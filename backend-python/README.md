# Advanced Timetable Generator Backend

This is a Python FastAPI backend for generating optimal timetables using genetic algorithms, supporting both lab and theory sessions with real-world constraints.

## Features

- **Mixed Session Types**: 2-hour continuous lab sessions and 1-hour theory sessions
- **Room Management**: Separate labs and classrooms with capacity constraints
- **Teacher Availability**: Support for teacher scheduling constraints
- **Course Enrollment**: Room capacity matching based on course enrollment
- **Multi-section Support**: Generate timetables for multiple sections simultaneously
- **Advanced Optimization**: Genetic algorithm with enhanced fitness function
- **Real-world Constraints**: Teacher availability, room capacities, and enrollment balancing

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Start the server:
```bash
python main.py
```

The server will run on `http://localhost:8000`

## API Endpoints

- `GET /` - Health check
- `POST /api/generate` - Generate new timetable with constraints
- `POST /api/regenerate` - Regenerate with last parameters

## Usage

### Basic Structure
- **Lab courses**: 2 hours (2 slots) continuous sessions
- **Theory courses**: 1 hour (1 slot) sessions
- **Optimal ratio**: 40% labs, 60% theory sessions
- **Rooms**: LAB prefix for labs, ROOM prefix for classrooms

### Request Format
```json
{
  "days": 5,
  "slots_per_day": 8,
  "labs": ["Lab1", "Lab2", "Lab3"],
  "classrooms": ["Room1", "Room2", "Room3", "Room4"],
  "courses": ["Physics", "Chemistry", "Math", "Computer Science"],
  "course_types": {
    "Physics": "lab",
    "Chemistry": "lab", 
    "Math": "theory",
    "Computer Science": "lab"
  },
  "sections": ["SectionA", "SectionB"],
  "teachers_per_course": {
    "Physics": 2,
    "Chemistry": 2,
    "Math": 3,
    "Computer Science": 2
  },
  "course_durations": {
    "Physics": 2,
    "Chemistry": 2,
    "Math": 1,
    "Computer Science": 2
  },
  "teacher_availability": {
    "T1": ["0|3", "0|4", "1|3", "1|4"],
    "T2": ["2|3", "2|4", "3|3", "3|4"]
  },
  "room_capacities": {
    "Lab1": 30,
    "Lab2": 25,
    "Lab3": 30,
    "Room1": 40,
    "Room2": 35,
    "Room3": 40,
    "Room4": 35
  },
  "course_enrollments": {
    "Physics": 28,
    "Chemistry": 24,
    "Math": 38,
    "Computer Science": 28
  }
}
```

### Response Format
```json
{
  "timetables": {
    "SectionA": [
      [null, null, "Math - ROOM3 (T1)", "Physics - LAB1 (T1)", "Physics - LAB1 (T1)", null, null, null],
      [null, null, "Math - ROOM4 (T2)", "Chemistry - LAB2 (T1)", "Chemistry - LAB2 (T1)", null, null, null]
    ],
    "SectionB": [...]
  },
  "sections": ["SectionA", "SectionB"],
  "total_fitness": 15,
  "success": true,
  "message": "Timetable generated successfully"
}
```

## Constraints and Optimization

### Genetic Algorithm Features
- **Population Size**: 50 individuals
- **Generations**: 350 evolution cycles
- **Mutation Rate**: 15% for genetic diversity
- **Selection**: Tournament selection with elitism

### Fitness Function Optimizations
- **Lab Continuity**: Ensures 2-hour lab sessions are continuous
- **Room Conflicts**: Eliminates double-booking of rooms
- **Teacher Workload**: Balances teacher assignments
- **Session Balance**: Maintains optimal lab/theory ratio
- **Capacity Matching**: Ensures rooms can accommodate enrollments
- **Availability Compliance**: Respects teacher availability constraints

### Real-world Constraints
- **Teacher Availability**: Specify unavailable time slots for each teacher
- **Room Capacity**: Match room sizes with course enrollments
- **Session Types**: Automatic handling of lab vs theory session requirements
- **Multi-section Coordination**: Prevents room conflicts across sections

## Cell Format
Each cell in the timetable follows the format:
```
{Course} - {ROOM/LAB}{RoomID} (T{TeacherID})
```

Examples:
- `Physics - LAB1 (T1)` - Physics lab in Lab 1 with Teacher 1
- `Math - ROOM3 (T2)` - Math theory in Room 3 with Teacher 2

## Error Handling
- Returns detailed error messages for constraint violations
- Validates input parameters before processing
- Handles edge cases (insufficient rooms, overbooked teachers, etc.)
