from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import uvicorn

from services.genetic_algorithm import generate_timetable, regenerate_timetable
from services.timetable_ga_v2 import (
    api_validate,
    api_start_generation,
    api_status,
    api_result,
    build_timetable_pdf_bytes,
)


app = FastAPI(title="Lab Timetable Generator API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LegacyTimetableInput(BaseModel):
    days: int
    slots_per_day: int
    labs: List[str]
    classrooms: List[str]
    courses: List[str]
    course_types: Dict[str, str]  # "lab" or "theory" for each course
    sections: Optional[List[str]] = None
    teachers_per_course: Optional[Dict[str, int]] = None
    course_durations: Optional[Dict[str, int]] = None
    teacher_availability: Optional[Dict[str, List[str]]] = None  # Teacher ID -> ["day|slot", ...]
    room_capacities: Optional[Dict[str, int]] = None  # Room ID -> capacity
    course_enrollments: Optional[Dict[str, int]] = None  # Course -> enrollment count


class LegacyTimetableResponse(BaseModel):
    timetables: Dict[str, List[List[Optional[str]]]]
    sections: List[str]
    total_fitness: int
    success: bool
    message: str

@app.get("/")
async def root():
    return {"status": "OK", "service": "Lab Timetable GA Backend", "version": "2.0.0"}

@app.post("/api/generate", response_model=LegacyTimetableResponse)
async def generate_timetable_endpoint(input_data: LegacyTimetableInput):
    try:
        # Convert teacher availability from list to set
        teacher_availability_set = {}
        if input_data.teacher_availability:
            for teacher_id, slots in input_data.teacher_availability.items():
                teacher_availability_set[teacher_id] = set(slots)
        
        result = generate_timetable(
            days=input_data.days,
            slots_per_day=input_data.slots_per_day,
            labs=input_data.labs,
            classrooms=input_data.classrooms,
            courses=input_data.courses,
            course_types=input_data.course_types,
            sections=input_data.sections or ["Default"],
            teachers_per_course=input_data.teachers_per_course or {},
            course_durations=input_data.course_durations or {},
            teacher_availability=teacher_availability_set,
            room_capacities=input_data.room_capacities,
            course_enrollments=input_data.course_enrollments
        )
        return LegacyTimetableResponse(
            timetables=result["timetables"],
            sections=result["sections"],
            total_fitness=result["total_fitness"],
            success=True,
            message="Timetable generated successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/regenerate", response_model=LegacyTimetableResponse)
async def regenerate_endpoint():
    try:
        result = regenerate_timetable()
        return LegacyTimetableResponse(
            timetables=result["timetables"],
            sections=result["sections"],
            total_fitness=result["total_fitness"],
            success=True,
            message="Timetable regenerated successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------
# New v2 API (job-based)
# ---------------------------


@app.post("/api/validate")
async def validate_endpoint(payload: Dict[str, Any]):
    """Validate the new schema. Returns status ok or failed with can't generate <reason>."""
    result = api_validate(payload)
    # api_validate already formats the can't generate prefix
    return result


@app.post("/api/generate")
async def start_generate_endpoint(payload: Dict[str, Any]):
    """Start GA job for the new schema.

    If validation fails, response will be of the form:
    {"status":"failed","reason":"can't generate <reason>","details":{...}}
    Else: {"status":"started","job_id": "..."}
    """
    result = api_start_generation(payload)
    return result


@app.get("/api/generate/status/{job_id}")
async def generation_status_endpoint(job_id: str):
    return api_status(job_id)


@app.get("/api/generate/result/{job_id}")
async def generation_result_endpoint(job_id: str):
    result = api_result(job_id)
    return result


@app.get("/api/timetable/{job_id}/download")
async def download_timetable_pdf(job_id: str, format: str = "pdf"):
    if format != "pdf":
        raise HTTPException(status_code=400, detail="Only PDF format is supported")

    result = api_result(job_id)
    if not isinstance(result, dict) or result.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Job not completed or not found")

    pdf_bytes = build_timetable_pdf_bytes(result)
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=timetable_{job_id}.pdf"},
    )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
