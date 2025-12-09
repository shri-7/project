from __future__ import annotations

import threading
import time
import uuid
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple

# -----------------------------
# Data structures
# -----------------------------

@dataclass
class LunchBreak:
    enabled: bool
    day: str  # "all" or specific day index as string
    period: int


@dataclass
class SectionDef:
    id: str


@dataclass
class SubjectDef:
    id: str
    section_id: str
    type: str  # "theory" or "lab"
    hours_per_week: int


@dataclass
class FacultyDef:
    id: str
    specializations: List[str]


@dataclass
class Constraints:
    one_faculty_per_section_subject: bool
    faculty_cannot_teach_two_sections_at_same_time: bool
    lab_block_length: int


@dataclass
class GenerationSettings:
    population_size: int
    max_generations: int
    time_limit_seconds: int


# -----------------------------
# Job store
# -----------------------------

_jobs_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}


def _init_job(input_payload: Dict[str, Any]) -> str:
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "pending",
            "progress": 0.0,
            "best_fitness": None,
            "created_at": time.time(),
            "updated_at": time.time(),
            "input": input_payload,
            "result": None,
            "metrics": None,
            "explanation": [],
        }
    return job_id


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    with _jobs_lock:
        return _jobs.get(job_id)


def get_job_result(job_id: str) -> Optional[Dict[str, Any]]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        if job["status"] != "completed":
            return {"status": job["status"], "progress": job.get("progress", 0.0)}
        return job["result"]


# -----------------------------
# Validation logic
# -----------------------------

class ValidationError(Exception):
    def __init__(self, reason: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}


def _build_basic_structs(payload: Dict[str, Any]) -> Tuple[
    int,
    int,
    LunchBreak,
    List[SectionDef],
    List[SubjectDef],
    List[FacultyDef],
    Constraints,
    GenerationSettings,
]:
    days_per_week = payload["days_per_week"]
    periods_per_day = payload["periods_per_day"]

    lb_raw = payload.get("lunch_break", {}) or {}
    lunch = LunchBreak(
        enabled=bool(lb_raw.get("enabled", False)),
        day=str(lb_raw.get("day", "all")),
        period=int(lb_raw.get("period", 0)),
    )

    sections = [SectionDef(**s) for s in payload.get("sections", [])]
    subjects = [SubjectDef(**s) for s in payload.get("subjects", [])]
    faculty = [FacultyDef(**f) for f in payload.get("faculty", [])]

    c_raw = payload.get("constraints", {}) or {}
    constraints = Constraints(
        one_faculty_per_section_subject=bool(c_raw.get("one_faculty_per_section_subject", True)),
        faculty_cannot_teach_two_sections_at_same_time=bool(
            c_raw.get("faculty_cannot_teach_two_sections_at_same_time", True)
        ),
        lab_block_length=int(c_raw.get("lab_block_length", 2)),
    )

    g_raw = payload.get("generation_settings", {}) or {}
    gen_settings = GenerationSettings(
        population_size=int(g_raw.get("population_size", 100)),
        max_generations=int(g_raw.get("max_generations", 200)),
        time_limit_seconds=int(g_raw.get("time_limit_seconds", 20)),
    )

    return (
        days_per_week,
        periods_per_day,
        lunch,
        sections,
        subjects,
        faculty,
        constraints,
        gen_settings,
    )


def _available_slots_per_section(days: int, periods: int, lunch: LunchBreak) -> int:
    total = days * periods
    if not lunch.enabled:
        return total
    if lunch.day == "all":
        return total - days
    # lunch on specific day index (0-based string)
    try:
        day_idx = int(lunch.day)
    except ValueError:
        return total
    if 0 <= day_idx < days:
        return total - 1
    return total


def _count_lab_blocks_capacity(days: int, periods: int, lunch: LunchBreak, lab_block_len: int) -> int:
    blocks = 0
    for d in range(days):
        for p in range(periods - lab_block_len + 1):
            ok = True
            for k in range(lab_block_len):
                if lunch.enabled:
                    if lunch.day == "all" and p + k == lunch.period:
                        ok = False
                        break
                    if lunch.day != "all":
                        try:
                            day_idx = int(lunch.day)
                        except ValueError:
                            day_idx = -1
                        if d == day_idx and p + k == lunch.period:
                            ok = False
                            break
            if ok:
                blocks += 1
    return blocks


def validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    (
        days,
        periods,
        lunch,
        sections,
        subjects,
        faculty,
        constraints,
        gen_settings,
    ) = _build_basic_structs(payload)

    if days <= 0 or periods <= 0:
        raise ValidationError("invalid_days_or_periods", {"days": days, "periods": periods})

    # Map for fast lookup
    faculty_by_id = {f.id: f for f in faculty}

    # 1) faculty specialization / existence
    for subj in subjects:
        qualified = [f for f in faculty if subj.id in f.specializations]
        if not qualified:
            raise ValidationError(f"no_qualified_faculty_for_subject_{subj.id}")

    # 2) total required periods vs available slots (per section)
    available_per_section = _available_slots_per_section(days, periods, lunch)

    section_ids = [s.id for s in sections]
    by_section: Dict[str, List[SubjectDef]] = {sid: [] for sid in section_ids}
    for subj in subjects:
        by_section.setdefault(subj.section_id, []).append(subj)

    for sid, subj_list in by_section.items():
        theory_periods = sum(s.hours_per_week for s in subj_list if s.type == "theory")
        lab_hours = sum(s.hours_per_week for s in subj_list if s.type == "lab")
        if lab_hours % constraints.lab_block_length != 0:
            raise ValidationError(
                f"lab_hours_not_multiple_of_block_for_section_{sid}",
                {"section": sid, "lab_hours": lab_hours, "lab_block_length": constraints.lab_block_length},
            )
        lab_blocks = lab_hours // constraints.lab_block_length
        total_required_periods = theory_periods + lab_blocks * constraints.lab_block_length
        if total_required_periods > available_per_section:
            raise ValidationError("total_required_periods_exceed_available_slots", {
                "section": sid,
                "total_required_periods": total_required_periods,
                "available": available_per_section,
            })

    # 3) lab consecutive block capacity per section
    max_lab_blocks = _count_lab_blocks_capacity(days, periods, lunch, constraints.lab_block_length)
    for sid, subj_list in by_section.items():
        lab_hours = sum(s.hours_per_week for s in subj_list if s.type == "lab")
        lab_blocks = lab_hours // constraints.lab_block_length
        if lab_blocks > max_lab_blocks:
            raise ValidationError(f"lab_block_unavailable_for_section_{sid}", {
                "section": sid,
                "required_lab_blocks": lab_blocks,
                "max_lab_blocks": max_lab_blocks,
            })

    # 4) very rough faculty load feasibility
    total_slots = days * periods
    if lunch.enabled:
        total_slots -= days if lunch.day == "all" else 1

    # approximate required teaching load per faculty by specialization
    for f in faculty:
        required_periods = 0
        for subj in subjects:
            if subj.id in f.specializations:
                if subj.type == "theory":
                    required_periods += subj.hours_per_week
                else:
                    required_periods += subj.hours_per_week  # hours already in periods
        if required_periods > total_slots:
            raise ValidationError(f"faculty_{f.id}_double_booked", {
                "faculty": f.id,
                "required_periods": required_periods,
                "max_periods": total_slots,
            })

    return {"status": "ok"}


# -----------------------------
# GA implementation
# -----------------------------

# Representation: timetable[section_idx][day][period] = {"subject", "faculty", "type"} or None


def _empty_timetable(num_sections: int, days: int, periods: int):
    return [
        [[None for _ in range(periods)] for _ in range(days)]
        for _ in range(num_sections)
    ]


def _clone_timetable(tt):
    return [
        [[slot.copy() if slot is not None else None for slot in day] for day in section]
        for section in tt
    ]


def _initial_individual(
    sections: List[SectionDef],
    days: int,
    periods: int,
    lunch: LunchBreak,
    subjects: List[SubjectDef],
    faculty: List[FacultyDef],
    constraints: Constraints,
):
    sec_index = {s.id: idx for idx, s in enumerate(sections)}
    timetable = _empty_timetable(len(sections), days, periods)

    # For each subject, schedule required periods/blocks randomly
    for subj in subjects:
        s_idx = sec_index[subj.section_id]
        qualified_faculty = [f for f in faculty if subj.id in f.specializations]
        if not qualified_faculty:
            continue
        chosen_faculty = random.choice(qualified_faculty)

        if subj.type == "theory":
            periods_needed = subj.hours_per_week
            while periods_needed > 0:
                d = random.randrange(days)
                p = random.randrange(periods)
                if lunch.enabled:
                    if lunch.day == "all" and p == lunch.period:
                        continue
                    if lunch.day != "all":
                        try:
                            day_idx = int(lunch.day)
                        except ValueError:
                            day_idx = -1
                        if d == day_idx and p == lunch.period:
                            continue
                if timetable[s_idx][d][p] is None:
                    timetable[s_idx][d][p] = {
                        "subject": subj.id,
                        "faculty": chosen_faculty.id,
                        "type": subj.type,
                    }
                    periods_needed -= 1
        else:  # lab
            blocks = subj.hours_per_week // constraints.lab_block_length
            for _ in range(blocks):
                placed = False
                for _ in range(100):
                    d = random.randrange(days)
                    p = random.randrange(periods - constraints.lab_block_length + 1)
                    ok = True
                    for k in range(constraints.lab_block_length):
                        if lunch.enabled:
                            if lunch.day == "all" and p + k == lunch.period:
                                ok = False
                                break
                            if lunch.day != "all":
                                try:
                                    day_idx = int(lunch.day)
                                except ValueError:
                                    day_idx = -1
                                if d == day_idx and p + k == lunch.period:
                                    ok = False
                                    break
                        if timetable[s_idx][d][p + k] is not None:
                            ok = False
                            break
                    if ok:
                        for k in range(constraints.lab_block_length):
                            timetable[s_idx][d][p + k] = {
                                "subject": subj.id,
                                "faculty": chosen_faculty.id,
                                "type": subj.type,
                            }
                        placed = True
                        break
                if not placed:
                    # leave unscheduled; fitness will penalize later
                    pass

    return timetable


def _fitness(
    timetable,
    sections: List[SectionDef],
    days: int,
    periods: int,
    lunch: LunchBreak,
    subjects: List[SubjectDef],
    faculty: List[FacultyDef],
    constraints: Constraints,
) -> Tuple[float, Dict[str, Any]]:
    hard_penalty = 0.0
    soft_penalty = 0.0

    sec_index = {s.id: idx for idx, s in enumerate(sections)}

    # Map required counts
    required_counts: Dict[Tuple[str, str], int] = {}
    for subj in subjects:
        if subj.type == "theory":
            required_counts[(subj.section_id, subj.id)] = subj.hours_per_week
        else:
            required_counts[(subj.section_id, subj.id)] = subj.hours_per_week

    actual_counts: Dict[Tuple[str, str], int] = {}

    # Teacher load tracking
    teacher_load: Dict[str, int] = {}

    # Hard constraints: teacher double-booked, lab not contiguous, lunch overlap
    for d in range(days):
        # track teacher usage per period across sections
        for p in range(periods):
            teachers_here: Dict[str, int] = {}
            for s_idx, _ in enumerate(sections):
                slot = timetable[s_idx][d][p]
                if slot is None:
                    continue
                subj_id = slot["subject"]
                fac_id = slot["faculty"]
                key = (sections[s_idx].id, subj_id)
                actual_counts[key] = actual_counts.get(key, 0) + 1

                teacher_load[fac_id] = teacher_load.get(fac_id, 0) + 1

                # lunch overlap
                if lunch.enabled:
                    if lunch.day == "all" and p == lunch.period:
                        hard_penalty += 50
                    elif lunch.day != "all":
                        try:
                            day_idx = int(lunch.day)
                        except ValueError:
                            day_idx = -1
                        if d == day_idx and p == lunch.period:
                            hard_penalty += 50

                teachers_here[fac_id] = teachers_here.get(fac_id, 0) + 1

            # teacher double-booked same period across sections
            for fac_id, cnt in teachers_here.items():
                if cnt > 1:
                    hard_penalty += 100 * (cnt - 1)

        # lab contiguity per section per day
        for s_idx, _ in enumerate(sections):
            p = 0
            while p < periods:
                slot = timetable[s_idx][d][p]
                if slot and slot["type"] == "lab":
                    # should have a contiguous block of given length
                    for k in range(constraints.lab_block_length):
                        if p + k >= periods:
                            hard_penalty += 100
                            break
                        s2 = timetable[s_idx][d][p + k]
                        if not s2 or s2["subject"] != slot["subject"] or s2["type"] != "lab":
                            hard_penalty += 100
                            break
                    p += constraints.lab_block_length
                else:
                    p += 1

    # Soft: teacher load imbalance, free periods, unmet required counts
    # unmet/mismatch counts
    for key, req in required_counts.items():
        act = actual_counts.get(key, 0)
        if act != req:
            hard_penalty += 20 * abs(req - act)

    # teacher load imbalance
    if teacher_load:
        loads = list(teacher_load.values())
        avg = sum(loads) / len(loads)
        var = sum((x - avg) ** 2 for x in loads) / len(loads)
        soft_penalty += var

    # too many free periods in a section day
    for s_idx, _ in enumerate(sections):
        for d in range(days):
            free = sum(1 for p in range(periods) if timetable[s_idx][d][p] is None)
            if free > periods // 2:
                soft_penalty += free - periods // 2

    total_penalty = hard_penalty * 1000 + soft_penalty

    # derive metrics
    fitness_score = max(0.0, 100000.0 - total_penalty)
    max_possible = 100000.0
    accuracy_percent = max(0.0, min(100.0, fitness_score / max_possible * 100.0))

    # workload stddev
    teacher_workload_stddev = 0.0
    if teacher_load:
        loads = list(teacher_load.values())
        avg = sum(loads) / len(loads)
        var = sum((x - avg) ** 2 for x in loads) / len(loads)
        teacher_workload_stddev = var ** 0.5

    # simple lab contiguity score (percentage of lab slots part of proper block)
    total_lab_slots = 0
    good_lab_slots = 0
    for s_idx, _ in enumerate(sections):
        for d in range(days):
            for p in range(periods):
                slot = timetable[s_idx][d][p]
                if slot and slot["type"] == "lab":
                    total_lab_slots += 1
                    ok = True
                    for k in range(constraints.lab_block_length):
                        if p + k >= periods:
                            ok = False
                            break
                        s2 = timetable[s_idx][d][p + k]
                        if not s2 or s2["subject"] != slot["subject"] or s2["type"] != "lab":
                            ok = False
                            break
                    if ok:
                        good_lab_slots += 1
    lab_contiguity_score = 100.0 if total_lab_slots == 0 else 100.0 * good_lab_slots / total_lab_slots

    metrics = {
        "fitness_score": fitness_score,
        "accuracy_percent": accuracy_percent,
        "teacher_workload_stddev": teacher_workload_stddev,
        "lab_contiguity_score": lab_contiguity_score,
    }

    return total_penalty, metrics


def _crossover(parent_a, parent_b):
    # swap random day blocks between parents
    days = len(parent_a[0])
    periods = len(parent_a[0][0]) if days > 0 else 0
    num_sections = len(parent_a)
    child = _clone_timetable(parent_a)

    day_cut = random.randrange(days) if days > 0 else 0
    for s in range(num_sections):
        for d in range(day_cut, days):
            for p in range(periods):
                child[s][d][p] = parent_b[s][d][p].copy() if parent_b[s][d][p] else None
    return child


def _mutate(individual, sections, days, periods, lunch: LunchBreak, subjects, faculty, constraints: Constraints, rate: float = 0.2):
    child = _clone_timetable(individual)
    num_sections = len(sections)

    # mutation 1: move random class
    if random.random() < rate:
        s_idx = random.randrange(num_sections)
        d1 = random.randrange(days)
        p1 = random.randrange(periods)
        d2 = random.randrange(days)
        p2 = random.randrange(periods)
        child[s_idx][d1][p1], child[s_idx][d2][p2] = child[s_idx][d2][p2], child[s_idx][d1][p1]

    # mutation 2: swap faculty for a random slot (within specialization)
    if random.random() < rate:
        s_idx = random.randrange(num_sections)
        d = random.randrange(days)
        p = random.randrange(periods)
        slot = child[s_idx][d][p]
        if slot:
            subj_id = slot["subject"]
            qualified = [f for f in faculty if subj_id in f.specializations]
            if qualified:
                new_f = random.choice(qualified)
                slot["faculty"] = new_f.id

    # mutation 3: try to shift labs into valid contiguous positions
    for s_idx in range(num_sections):
        for d in range(days):
            p = 0
            while p < periods:
                slot = child[s_idx][d][p]
                if slot and slot["type"] == "lab" and random.random() < rate:
                    subj_id = slot["subject"]
                    fac_id = slot["faculty"]
                    # clear current block
                    for k in range(constraints.lab_block_length):
                        if p + k < periods and child[s_idx][d][p + k] and child[s_idx][d][p + k]["subject"] == subj_id:
                            child[s_idx][d][p + k] = None
                    # try place somewhere else
                    for _ in range(20):
                        nd = random.randrange(days)
                        np = random.randrange(periods - constraints.lab_block_length + 1)
                        ok = True
                        for k in range(constraints.lab_block_length):
                            if child[s_idx][nd][np + k] is not None:
                                ok = False
                                break
                            if lunch.enabled:
                                if lunch.day == "all" and np + k == lunch.period:
                                    ok = False
                                    break
                                if lunch.day != "all":
                                    try:
                                        day_idx = int(lunch.day)
                                    except ValueError:
                                        day_idx = -1
                                    if nd == day_idx and np + k == lunch.period:
                                        ok = False
                                        break
                        if ok:
                            for k in range(constraints.lab_block_length):
                                child[s_idx][nd][np + k] = {
                                    "subject": subj_id,
                                    "faculty": fac_id,
                                    "type": "lab",
                                }
                            break
                    p += constraints.lab_block_length
                else:
                    p += 1

    return child


def _run_ga_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        payload = job["input"]

    (
        days,
        periods,
        lunch,
        sections,
        subjects,
        faculty,
        constraints,
        gen_settings,
    ) = _build_basic_structs(payload)

    population_size = gen_settings.population_size
    max_generations = gen_settings.max_generations
    time_limit = gen_settings.time_limit_seconds

    # init population
    population = []
    for _ in range(population_size):
        ind = _initial_individual(sections, days, periods, lunch, subjects, faculty, constraints)
        score, metrics = _fitness(ind, sections, days, periods, lunch, subjects, faculty, constraints)
        population.append({"tt": ind, "score": score, "metrics": metrics})

    best = min(population, key=lambda x: x["score"])
    start_time = time.time()

    with _jobs_lock:
        _jobs[job_id]["status"] = "running"
        _jobs[job_id]["best_fitness"] = best["metrics"]["fitness_score"]
        _jobs[job_id]["progress"] = 0.0
        _jobs[job_id]["updated_at"] = time.time()

    generation = 0
    last_improvement_gen = 0

    while generation < max_generations and (time.time() - start_time) < time_limit:
        generation += 1
        new_population = []
        # elitism
        population.sort(key=lambda x: x["score"])
        new_population.extend(population[:2])

        while len(new_population) < population_size:
            parents = random.sample(population[: max(3, population_size // 2)], 2)
            child_tt = _crossover(parents[0]["tt"], parents[1]["tt"])
            child_tt = _mutate(
                child_tt,
                sections,
                days,
                periods,
                lunch,
                subjects,
                faculty,
                constraints,
                rate=0.2,
            )
            score, metrics = _fitness(child_tt, sections, days, periods, lunch, subjects, faculty, constraints)
            new_population.append({"tt": child_tt, "score": score, "metrics": metrics})

        population = new_population
        current_best = min(population, key=lambda x: x["score"])
        if current_best["score"] < best["score"]:
            best = current_best
            last_improvement_gen = generation

        progress = generation / max_generations
        with _jobs_lock:
            if job_id not in _jobs:
                return
            _jobs[job_id]["best_fitness"] = best["metrics"]["fitness_score"]
            _jobs[job_id]["progress"] = progress
            _jobs[job_id]["updated_at"] = time.time()

        # early stop if stable
        if generation - last_improvement_gen > max_generations // 5:
            break

    # finalize
    timetable = {}
    for idx, s in enumerate(sections):
        timetable[s.id] = {"matrix": best["tt"][idx]}

    result = {
        "status": "completed",
        "fitness_score": best["metrics"]["fitness_score"],
        "accuracy_percent": best["metrics"]["accuracy_percent"],
        "timetable": {"sections": timetable},
        "metrics": best["metrics"],
        "explanation": [
            "Timetable generated using genetic algorithm with day-block crossover and mutation operators.",
            f"Generations processed: {generation}",
            f"Population size: {population_size}",
        ],
    }

    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["result"] = result
            _jobs[job_id]["metrics"] = best["metrics"]
            _jobs[job_id]["updated_at"] = time.time()


def start_generation_job(payload: Dict[str, Any]) -> str:
    # assumes payload already validated
    job_id = _init_job(payload)
    t = threading.Thread(target=_run_ga_job, args=(job_id,), daemon=True)
    t.start()
    return job_id


# -----------------------------
# Public API helpers for FastAPI layer
# -----------------------------


def api_validate(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return validate_payload(payload)
    except ValidationError as e:
        return {
            "status": "failed",
            "reason": f"can't generate {e.reason}",
            "details": e.details,
        }


def api_start_generation(payload: Dict[str, Any]) -> Dict[str, Any]:
    # run validation first
    v = api_validate(payload)
    if v.get("status") != "ok":
        return v
    job_id = start_generation_job(payload)
    return {"status": "started", "job_id": job_id}


def api_status(job_id: str) -> Dict[str, Any]:
    job = get_job_status(job_id)
    if not job:
        return {"status": "not_found"}
    return {
        "status": job["status"],
        "progress": job.get("progress", 0.0),
        "best_fitness": job.get("best_fitness"),
    }


def api_result(job_id: str) -> Dict[str, Any]:
    job = get_job_status(job_id)
    if not job:
        return {"status": "not_found"}
    if job["status"] != "completed":
        return {"status": job["status"], "progress": job.get("progress", 0.0)}
    return job["result"]


def build_timetable_pdf_bytes(timetable_result: Dict[str, Any]) -> bytes:
    """Build a very simple PDF representation of the timetable using reportlab if available.

    If reportlab is not installed, returns a minimal placeholder PDF bytestring.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        import io

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        y = height - 40
        c.setFont("Helvetica-Bold", 14)
        c.drawString(40, y, "Generated Timetable")
        y -= 30

        metrics = timetable_result.get("metrics", {})
        c.setFont("Helvetica", 10)
        for key, value in metrics.items():
            c.drawString(40, y, f"{key}: {value}")
            y -= 14

        y -= 10
        sections = timetable_result.get("timetable", {}).get("sections", {})
        for sid, data in sections.items():
            matrix = data.get("matrix", [])
            c.setFont("Helvetica-Bold", 12)
            c.drawString(40, y, f"Section {sid}")
            y -= 18
            c.setFont("Helvetica", 8)
            for day_idx, day in enumerate(matrix):
                row_text = f"Day {day_idx + 1}: "
                cells = []
                for slot in day:
                    if slot is None:
                        cells.append("-")
                    else:
                        cells.append(f"{slot.get('subject')}({slot.get('faculty')})")
                row_text += " | ".join(cells)
                c.drawString(40, y, row_text[:200])
                y -= 12
                if y < 60:
                    c.showPage()
                    y = height - 40

            y -= 16
            if y < 60:
                c.showPage()
                y = height - 40

        c.showPage()
        c.save()
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes
    except Exception:
        # Fallback minimal PDF
        return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
