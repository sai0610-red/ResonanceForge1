# SOP MR-014: Work-order priority assignment (Red River Components, fictional)

Owner: Maintenance Planning. Applies to both plants.

## Priority definitions

- P1: Safety hazard, environmental release, or a constraint press / CNC cell down. Response within 1 hour. Requires a supervisor call, not just a ticket.
- P2: Asset running degraded with risk of failure inside 24 hours (for example, hydraulic leak on a stamping press, spindle vibration alarm). Response within 8 hours.
- P3: Planned corrective work that can wait for the next scheduled window. Response within 5 working days.
- P4: Cosmetic, housekeeping, or improvement requests. No SLA.

## Who can change a priority

Only a maintenance planner or the maintenance supervisor may change the priority of an open work order. Every change must have a reason code entered in the work-order notes. Operators may request a change but may not make it.

## Daily exception review

Each morning at 06:30 the on-shift planner runs the CMMS "Open exceptions" saved query (missed SLA, waiting on parts, no assigned technician). Exceptions are triaged in this order: safety first, then constraint assets, then oldest P2.

## Parts holds

A work order may be set to "Waiting on parts" only when a purchase requisition number is entered. Planners check the ERP purchasing screen by hand because the CMMS stock figure comes from the nightly batch and is often stale by the afternoon.

## Audit

The reliability engineer samples 20 priority changes per month to check reason codes. Findings go to the monthly maintenance review.
