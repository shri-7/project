# Multi-Section Timetable Generation - Architecture & Logic Flow

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   FRONTEND (React)                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  InputForm.jsx                                              │
│  ├─ days, slots, rooms, courses, sections (optional)       │
│  └─ teachersPerCourse                                      │
│         │                                                  │
│         │ POST /api/generate                              │
│         ▼                                                  │
│  API Call → Backend                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                           │
                           │
┌─────────────────────────────────────────────────────────────┐
│                   BACKEND (Node.js/Express)               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  gaController.js                                            │
│  ├─ Extract sections from request                          │
│  ├─ If empty, use ['Default']                             │
│  └─ Call runGA with all parameters                        │
│         │                                                  │
│         ▼                                                  │
│  ga.js - runGA()                                           │
│  ├─ For each section sequentially:                        │
│  │  ├─ 1. Track room usage from previous sections         │
│  │  ├─ 2. Initialize population (50 individuals)          │
│  │  │   └─ Each checks room availability                  │
│  │  ├─ 3. Run 350 generations:                            │
│  │  │   ├─ Sort by fitness                                │
│  │  │   ├─ Keep top 5 (elitism)                           │
│  │  │   ├─ Fill remaining 45 via:                         │
│  │  │   │  ├─ Tournament selection (k=3)                  │
│  │  │   │  └─ Mutation (respects room constraints)        │
│  │  │   └─ Evaluate fitness against other sections        │
│  │  └─ 4. Store best timetable for section                │
│  │                                                         │
│  └─ Return multi-section result                           │
│         │                                                  │
│         │ Response with timetables, sections, totalFitness│
│         ▼                                                  │
│  JSON Response                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                           │
                           │
┌─────────────────────────────────────────────────────────────┐
│                   FRONTEND (React)                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Timetable.jsx                                              │
│  ├─ Detect result format                                  │
│  ├─ If result.timetables exists (new format):            │
│  │  ├─ For each section in result.sections:              │
│  │  │  └─ Render TableRenderer with that section's TT    │
│  │  └─ Display totalFitness score                        │
│  └─ Else if result.timetable exists (old format):        │
│     └─ Render single table (backward compatible)         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Key Algorithm: Room Constraint Handling

### Problem
- Multiple sections need timetables
- Same room cannot be used by different sections simultaneously
- Want optimal schedule with minimum conflicts

### Solution: Sequential Generation with Constraint Tracking

```
Step 1: Generate Section A
┌──────────────┬──────────────┬──────────────┐
│ Day 1 Slot 1 │ Day 1 Slot 2 │ Day 1 Slot 3 │
├──────────────┼──────────────┼──────────────┤
│    R1        │    R2        │    R3        │
├──────────────┼──────────────┼──────────────┤
│ Day 2 Slot 1 │ Day 2 Slot 2 │ Day 2 Slot 3 │
├──────────────┼──────────────┼──────────────┤
│    R3        │    R1        │    R2        │
└──────────────┴──────────────┴──────────────┘

Step 2: Track Room Usage from Section A
usedRooms = {
  "0|0": {R1},
  "0|1": {R2},
  "0|2": {R3},
  "1|0": {R3},
  "1|1": {R1},
  "1|2": {R2}
}

Step 3: Generate Section B (avoiding rooms used in Step 2)
┌──────────────┬──────────────┬──────────────┐
│ Day 1 Slot 1 │ Day 1 Slot 2 │ Day 1 Slot 3 │
├──────────────┼──────────────┼──────────────┤
│    R2        │    R3        │    R1        │  ← Different from A
├──────────────┼──────────────┼──────────────┤
│ Day 2 Slot 1 │ Day 2 Slot 2 │ Day 2 Slot 3 │
├──────────────┼──────────────┼──────────────┤
│    R1        │    R3        │    R2        │  ← Different from A
└──────────────┴──────────────┴──────────────┘

RESULT: No room conflicts between sections
```

## Fitness Function: Multi-Objective Optimization

### Per-Section Penalties
```
For each day and slot:
  1. Course Repeat Penalty = 1 point
     └─ If same course scheduled >1 time per day
  
  2. Adjacent Room Penalty = 1 point
     └─ If same room in consecutive slots same day
  
  3. Teacher Reuse Penalty = 1 point
     └─ If same teacher teaches same course >1 time per day
```

### Cross-Section Penalties
```
For each day and slot across all sections:
  4. Room Conflict Penalty = 5 points
     └─ If same room booked in multiple sections simultaneously
     └─ (HIGH penalty to prioritize constraint satisfaction)
```

### Example Calculation
```
Section A fitness = 2 (1 course repeat + 1 adjacent room)
Section B fitness = 1 (1 teacher reuse)
Room conflict = 3 × 5 = 15 (3 time slots with conflicts)

Total Fitness = 2 + 1 + 15 = 18
(Lower is better - GA minimizes this)
```

## Genetic Algorithm Evolution (Per Section)

```
Generation 0: Random Population (50 individuals)
│
│ Evaluate Fitness for all
│ (considering other sections)
│
├─► Sort by Fitness
│
├─► Elitism: Keep Top 5 Best
│
├─► Selection: Tournament (k=3)
│   └─ Randomly pick 3 candidates
│   └─ Select the one with best fitness
│
├─► Mutation (45 offspring needed)
│   ├─ 60% probability: Swap two random cells
│   └─ 15% mutation rate per cell:
│       ├─ Pick random course
│       ├─ Pick available room (not used in that slot)
│       └─ Pick random teacher
│
└─► Repeat 350 times
    (Each generation refines the schedule)

Final Output: Best individual found
```

## Data Structures

### Room Usage Tracking
```javascript
usedRooms = Map<string, Set<string>>
  Key: "${day}|${slot}"  // e.g., "0|0", "0|1"
  Value: Set of room names already assigned to that slot
  
Example:
{
  "0|0": Set("R1", "R2"),      // Rooms R1 and R2 used
  "0|1": Set("R3"),            // Only R3 used
  "0|2": Set("R1"),            // Only R1 used
  ...
}
```

### Result Structure
```javascript
{
  timetables: {
    "SectionA": [
      [cell, cell, cell, ...],  // Day 0
      [cell, cell, cell, ...],  // Day 1
      ...
    ],
    "SectionB": [...],
    "SectionC": [...]
  },
  sections: ["SectionA", "SectionB", "SectionC"],
  totalFitness: 42  // Combined fitness across all sections
}

// Each cell format: "COURSE - ROOM (TID)"
// Example: "DBMS - R1 (T1)"
```

## Performance Characteristics

### Time Complexity
- **Per Section**: O(GENERATIONS × POP_SIZE × GENOME_LENGTH)
- **Total**: O(num_sections × 350 × 50 × (days × slots))
- **With 5 sections, 5 days, 6 slots**: ~5 × 350 × 50 × 30 = 2.625M operations

### Space Complexity
- **Population**: O(POP_SIZE × days × slots) = 50 × 30 = 1500 cells per section
- **Room Usage Map**: O(days × slots) = 30 entries per section
- **Overall**: O(num_sections × (1500 + 30)) = ~1500 cells per section

## Constraint Satisfaction Guarantee

### How Room Conflicts are Prevented

```
1. INITIALIZATION PHASE
   └─ randomTimetable() checks usedRooms before assignment
   └─ Only picks rooms not in usedRooms[day|slot]

2. MUTATION PHASE
   └─ mutate() checks usedRooms before assignment
   └─ availableRooms = all_rooms - usedRooms[day|slot]
   └─ Randomly selects from availableRooms

3. FITNESS EVALUATION
   └─ Penalty of 5 for any conflicts that slip through
   └─ GA pressure drives these to zero over generations

4. SEQUENTIAL GENERATION
   └─ Each section locks in before next section starts
   └─ Creates cascading constraint propagation
   └─ Later sections face harder constraints (fewer rooms)
```

### Feasibility Considerations
- **Feasible if**: num_sections ≤ num_rooms
  - Each section can get exclusive room(s)
- **Challenged if**: num_sections > num_rooms
  - Must share rooms across time slots
  - Algorithm still finds good solutions via fitness pressure

## Example Workflow

### Input
```json
{
  "days": 2,
  "slots": 3,
  "rooms": ["R1", "R2"],
  "courses": ["Math", "Physics"],
  "sections": ["A", "B"],
  "teachersPerCourse": {"Math": 1, "Physics": 1}
}
```

### Processing
1. **Section A** (No constraints, all rooms available)
   - Generates optimal timetable
   - UsedRooms populated with A's assignments

2. **Section B** (Must avoid A's assignments)
   - Avoids rooms already used by A at same time
   - May reuse rooms at different times
   - Evolves to minimize conflicts

### Output
```json
{
  "timetables": {
    "A": [
      ["Math - R1 (T1)", "Physics - R2 (T1)", "Math - R1 (T1)"],
      ["Physics - R2 (T1)", "Math - R1 (T1)", "Physics - R2 (T1)"]
    ],
    "B": [
      ["Physics - R2 (T1)", "Math - R1 (T1)", "Physics - R2 (T1)"],
      ["Math - R1 (T1)", "Physics - R2 (T1)", "Math - R1 (T1)"]
    ]
  ],
  "sections": ["A", "B"],
  "totalFitness": 8
}
```

**✓ No room conflicts**: Each (day, slot) uses different rooms for A and B
