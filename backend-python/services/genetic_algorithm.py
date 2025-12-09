import random
import numpy as np
import re
from typing import List, Dict, Tuple, Optional
from copy import deepcopy
import json

# Global storage for last input
last_input = None

def set_last_input(input_data: Dict):
    global last_input
    last_input = input_data

def get_last_input() -> Optional[Dict]:
    global last_input
    return last_input

def parse_cell(cell: Optional[str]) -> Dict[str, str]:
    """Parse a cell to extract course, room, type, and teacher information."""
    if not cell:
        return {"course": "", "room": "", "type": "", "teacher": ""}
    
    parts = cell.split(" - ")
    course = parts[0] if parts else ""
    rest = parts[1] if len(parts) > 1 else ""
    
    # Extract room and type
    room = ""
    course_type = ""
    if rest:
        if rest.startswith("LAB"):
            course_type = "lab"
            room = rest[3:].split(" ")[0]  # Remove "LAB" prefix
        elif rest.startswith("ROOM"):
            course_type = "theory"
            room = rest[4:].split(" ")[0]  # Remove "ROOM" prefix
    
    # Extract teacher info
    teacher_match = re.search(r"\(T(\d+)\)", cell)
    teacher = f"T{teacher_match.group(1)}" if teacher_match else ""
    
    return {"course": course, "room": room, "type": course_type, "teacher": teacher}

def generate_random_timetable(days: int, slots_per_day: int, labs: List[str], classrooms: List[str],
                               courses: List[str], course_types: Dict[str, str], teachers_per_course: Dict[str, int],
                               course_durations: Dict[str, int], used_labs: Dict[str, set], used_classrooms: Dict[str, set],
                               teacher_availability: Optional[Dict[str, set]] = None, 
                               room_capacities: Optional[Dict[str, int]] = None,
                               course_enrollments: Optional[Dict[str, int]] = None) -> List[List[Optional[str]]]:
    """Generate a random timetable considering lab and classroom constraints with real-world constraints."""
    timetable = [[None for _ in range(slots_per_day)] for _ in range(days)]
    
    for day in range(days):
        for slot in range(slots_per_day):
            # Skip if already filled by multi-slot session
            if timetable[day][slot]:
                continue
            
            # Select a course and determine its type and duration
            course = random.choice(courses)
            course_type = course_types.get(course, "lab")  # Default to lab
            duration = max(1, course_durations.get(course, 2 if course_type == "lab" else 1))
            
            # Adjust duration if it doesn't fit remaining slots
            if slot + duration > slots_per_day:
                duration = 1
            
            # Find available room based on course type and capacity
            if course_type == "lab":
                available_rooms = []
                for lab in labs:
                    room_available = True
                    # Check room capacity
                    if room_capacities and course_enrollments:
                        if room_capacities.get(lab, 0) < course_enrollments.get(course, 0):
                            room_available = False
                    # Check availability for all duration slots
                    for k in range(duration):
                        key = f"{day}|{slot + k}"
                        if lab in used_labs.get(key, set()):
                            room_available = False
                            break
                    if room_available:
                        available_rooms.append(lab)
                selected_room = random.choice(available_rooms) if available_rooms else random.choice(labs)
                room_prefix = "LAB"
            else:  # theory
                available_rooms = []
                for classroom in classrooms:
                    room_available = True
                    # Check room capacity
                    if room_capacities and course_enrollments:
                        if room_capacities.get(classroom, 0) < course_enrollments.get(course, 0):
                            room_available = False
                    # Check availability for all duration slots
                    for k in range(duration):
                        key = f"{day}|{slot + k}"
                        if classroom in used_classrooms.get(key, set()):
                            room_available = False
                            break
                    if room_available:
                        available_rooms.append(classroom)
                selected_room = random.choice(available_rooms) if available_rooms else random.choice(classrooms)
                room_prefix = "ROOM"
            
            # Assign teacher with availability check
            teacher_count = max(1, teachers_per_course.get(course, 1))
            available_teachers = []
            
            for teacher_idx in range(1, teacher_count + 1):
                teacher_id = f"T{teacher_idx}"
                teacher_available = True
                
                # Check teacher availability
                if teacher_availability and teacher_id in teacher_availability:
                    for k in range(duration):
                        key = f"{day}|{slot + k}"
                        if key in teacher_availability[teacher_id]:
                            teacher_available = False
                            break
                
                if teacher_available:
                    available_teachers.append(teacher_idx)
            
            teacher_idx = random.choice(available_teachers) if available_teachers else random.randint(1, teacher_count)
            
            cell_value = f"{course} - {room_prefix}{selected_room} (T{teacher_idx})"
            
            # Place the session across duration slots
            for k in range(duration):
                timetable[day][slot + k] = cell_value
                key = f"{day}|{slot + k}"
                if course_type == "lab":
                    if key not in used_labs:
                        used_labs[key] = set()
                    used_labs[key].add(selected_room)
                else:
                    if key not in used_classrooms:
                        used_classrooms[key] = set()
                    used_classrooms[key].add(selected_room)
    
    return timetable

def calculate_fitness(timetable: List[List[Optional[str]]], all_section_timetables: List[List[List[Optional[str]]]],
                    teacher_availability: Optional[Dict[str, set]] = None,
                    room_capacities: Optional[Dict[str, int]] = None,
                    course_enrollments: Optional[Dict[str, int]] = None) -> int:
    """Calculate fitness score (lower is better) for a timetable with real-world constraints."""
    penalty = 0
    
    # Check within single timetable
    for day in range(len(timetable)):
        seen_courses = {}
        seen_course_teacher = {}
        lab_count = 0
        theory_count = 0
        
        for slot in range(len(timetable[day])):
            cell_info = parse_cell(timetable[day][slot])
            course = cell_info["course"]
            room = cell_info["room"]
            course_type = cell_info["type"]
            teacher = cell_info["teacher"]
            
            # Count lab and theory sessions for balance
            if course:
                if course_type == "lab":
                    lab_count += 1
                else:
                    theory_count += 1
            
            # Penalty for same course appearing multiple times per day
            if course:
                seen_courses[course] = seen_courses.get(course, 0) + 1
                if seen_courses[course] > 1:
                    penalty += 2  # Higher penalty for duplicate courses
            
            # Penalty for same room in adjacent slots (should be avoided)
            if slot > 0:
                prev_room = parse_cell(timetable[day][slot - 1])["room"]
                if prev_room == room and room:
                    penalty += 1
            
            # Penalty for same teacher teaching same course multiple times per day
            if course and teacher:
                key = f"{course}|{teacher}"
                seen_course_teacher[key] = seen_course_teacher.get(key, 0) + 1
                if seen_course_teacher[key] > 1:
                    penalty += 3  # High penalty for teacher redundancy
            
            # Penalty for lab sessions not being continuous (2-hour blocks)
            if course_type == "lab" and slot > 0:
                prev_cell = parse_cell(timetable[day][slot - 1])
                if prev_cell["course"] != course or prev_cell["type"] != "lab":
                    # Check if this is the start of a lab session
                    if slot + 1 < len(timetable[day]):
                        next_cell = parse_cell(timetable[day][slot + 1])
                        if next_cell["course"] != course or next_cell["type"] != "lab":
                            penalty += 5  # High penalty for non-continuous lab sessions
            
            # Penalty for teacher availability violations
            if teacher and teacher_availability and teacher in teacher_availability:
                key = f"{day}|{slot}"
                if key in teacher_availability[teacher]:
                    penalty += 8  # High penalty for unavailable teachers
            
            # Penalty for room capacity violations
            if room and room_capacities and course_enrollments and course:
                if room_capacities.get(room, 0) < course_enrollments.get(course, 0):
                    penalty += 6  # High penalty for overcrowded rooms
        
        # Penalty for imbalance between lab and theory sessions
        total_sessions = lab_count + theory_count
        if total_sessions > 0:
            lab_ratio = lab_count / total_sessions
            # Ideal ratio is around 40% labs, 60% theory
            ratio_penalty = abs(lab_ratio - 0.4) * 10
            penalty += int(ratio_penalty)
    
    # Check for room conflicts across sections
    for other_timetable in all_section_timetables:
        for day in range(len(timetable)):
            for slot in range(len(timetable[day])):
                cell_info = parse_cell(timetable[day][slot])
                other_cell_info = parse_cell(other_timetable[day][slot])
                
                room = cell_info["room"]
                other_room = other_cell_info["room"]
                course_type = cell_info["type"]
                other_course_type = other_cell_info["type"]
                
                # High penalty for same room conflicts
                if room and other_room and room == other_room:
                    penalty += 10  # Very high penalty for room conflicts
    
    return penalty

def mutate_timetable(timetable: List[List[Optional[str]]], labs: List[str], classrooms: List[str],
                    courses: List[str], course_types: Dict[str, str], teachers_per_course: Dict[str, int], 
                    course_durations: Dict[str, int], used_labs: Dict[str, set], used_classrooms: Dict[str, set], 
                    mutation_rate: float = 0.2) -> List[List[Optional[str]]]:
    """Mutate a timetable by random changes."""
    mutated = deepcopy(timetable)
    days = len(mutated)
    slots_per_day = len(mutated[0]) if days > 0 else 0
    
    def is_start_slot(timetable_arr, day, slot):
        """Check if this is the start of a multi-slot session."""
        if slot == 0:
            return True
        return timetable_arr[day][slot] != timetable_arr[day][slot - 1]
    
    # Random cell swap
    if random.random() < 0.6:
        day1, slot1 = random.randint(0, days-1), random.randint(0, slots_per_day-1)
        day2, slot2 = random.randint(0, days-1), random.randint(0, slots_per_day-1)
        mutated[day1][slot1], mutated[day2][slot2] = mutated[day2][slot2], mutated[day1][slot1]
    
    # Random mutations at start slots only
    for day in range(days):
        for slot in range(slots_per_day):
            if not is_start_slot(mutated, day, slot):
                continue
                
            if random.random() < mutation_rate:
                course = random.choice(courses)
                course_type = course_types.get(course, "lab")
                duration = max(1, course_durations.get(course, 2 if course_type == "lab" else 1))
                
                if slot + duration > slots_per_day:
                    duration = 1
                
                # Find available room based on course type
                if course_type == "lab":
                    available_rooms = []
                    for lab in labs:
                        room_available = True
                        for k in range(duration):
                            key = f"{day}|{slot + k}"
                            if lab in used_labs.get(key, set()):
                                room_available = False
                                break
                        if room_available:
                            available_rooms.append(lab)
                    selected_room = random.choice(available_rooms) if available_rooms else random.choice(labs)
                    room_prefix = "LAB"
                else:  # theory
                    available_rooms = []
                    for classroom in classrooms:
                        room_available = True
                        for k in range(duration):
                            key = f"{day}|{slot + k}"
                            if classroom in used_classrooms.get(key, set()):
                                room_available = False
                                break
                        if room_available:
                            available_rooms.append(classroom)
                    selected_room = random.choice(available_rooms) if available_rooms else random.choice(classrooms)
                    room_prefix = "ROOM"
                
                teacher_count = max(1, teachers_per_course.get(course, 1))
                teacher_idx = random.randint(1, teacher_count)
                
                cell_value = f"{course} - {room_prefix}{selected_room} (T{teacher_idx})"
                
                # Place the mutated session
                for k in range(duration):
                    mutated[day][slot + k] = cell_value
    
    return mutated

def tournament_selection(population: List[Dict], k: int = 3) -> Dict:
    """Select best individual from tournament."""
    best = None
    for _ in range(k):
        individual = random.choice(population)
        if best is None or individual["fitness"] < best["fitness"]:
            best = individual
    return best

def generate_timetable(days: int, slots_per_day: int, labs: List[str], classrooms: List[str],
                      courses: List[str], course_types: Dict[str, str], sections: List[str], 
                      teachers_per_course: Dict[str, int], course_durations: Dict[str, int],
                      teacher_availability: Optional[Dict[str, set]] = None,
                      room_capacities: Optional[Dict[str, int]] = None,
                      course_enrollments: Optional[Dict[str, int]] = None) -> Dict:
    """Main function to generate timetable using genetic algorithm for both lab and theory sessions with real-world constraints."""
    POPULATION_SIZE = 50
    GENERATIONS = 350
    MUTATION_RATE = 0.15
    
    # Set default course durations (2 slots for labs, 1 slot for theory)
    for course in courses:
        if course not in course_durations:
            course_type = course_types.get(course, "lab")
            course_durations[course] = 2 if course_type == "lab" else 1
    
    set_last_input({
        "days": days,
        "slots_per_day": slots_per_day,
        "labs": labs,
        "classrooms": classrooms,
        "courses": courses,
        "course_types": course_types,
        "sections": sections,
        "teachers_per_course": teachers_per_course,
        "course_durations": course_durations,
        "teacher_availability": teacher_availability,
        "room_capacities": room_capacities,
        "course_enrollments": course_enrollments
    })
    
    section_timetables = {}
    
    for section in sections:
        # Track room usage across sections for conflict detection
        used_labs = {}
        used_classrooms = {}
        
        # Pre-populate used rooms from already generated sections
        for gen_section, gen_tt in section_timetables.items():
            for day in range(len(gen_tt)):
                for slot in range(len(gen_tt[day])):
                    cell_info = parse_cell(gen_tt[day][slot])
                    room = cell_info["room"]
                    course_type = cell_info["type"]
                    key = f"{day}|{slot}"
                    
                    if room:
                        if course_type == "lab":
                            if key not in used_labs:
                                used_labs[key] = set()
                            used_labs[key].add(room)
                        else:
                            if key not in used_classrooms:
                                used_classrooms[key] = set()
                            used_classrooms[key].add(room)
        
        # Initialize population
        population = []
        for _ in range(POPULATION_SIZE):
            timetable = generate_random_timetable(
                days, slots_per_day, labs, classrooms, courses, course_types, 
                teachers_per_course, course_durations, used_labs, used_classrooms,
                teacher_availability, room_capacities, course_enrollments
            )
            other_timetables = list(section_timetables.values())
            fitness = calculate_fitness(timetable, other_timetables, teacher_availability, room_capacities, course_enrollments)
            population.append({"timetable": timetable, "fitness": fitness})
        
        # Evolution
        for generation in range(GENERATIONS):
            population.sort(key=lambda x: x["fitness"])
            
            # Elitism - keep top 5
            next_generation = population[:5]
            
            # Fill rest via tournament selection and mutation
            while len(next_generation) < POPULATION_SIZE:
                parent = tournament_selection(population, 3)
                child_timetable = mutate_timetable(
                    parent["timetable"], labs, classrooms, courses, course_types,
                    teachers_per_course, course_durations, used_labs, used_classrooms, MUTATION_RATE
                )
                other_timetables = list(section_timetables.values())
                fitness = calculate_fitness(child_timetable, other_timetables, teacher_availability, room_capacities, course_enrollments)
                next_generation.append({"timetable": child_timetable, "fitness": fitness})
            
            population = next_generation
        
        # Select best timetable for this section
        population.sort(key=lambda x: x["fitness"])
        section_timetables[section] = population[0]["timetable"]
    
    # Calculate total fitness
    total_fitness = sum(
        calculate_fitness(tt, list(section_timetables.values()), teacher_availability, room_capacities, course_enrollments) 
        for tt in section_timetables.values()
    )
    
    return {
        "timetables": section_timetables,
        "sections": sections,
        "total_fitness": total_fitness
    }

def regenerate_timetable() -> Dict:
    """Regenerate timetable using last input parameters."""
    last_input_data = get_last_input()
    if not last_input_data:
        raise Exception("No previous input found. Call /api/generate first.")
    
    return generate_timetable(
        days=last_input_data["days"],
        slots_per_day=last_input_data["slots_per_day"],
        labs=last_input_data["labs"],
        classrooms=last_input_data["classrooms"],
        courses=last_input_data["courses"],
        course_types=last_input_data["course_types"],
        sections=last_input_data["sections"],
        teachers_per_course=last_input_data["teachers_per_course"],
        course_durations=last_input_data["course_durations"]
    )
