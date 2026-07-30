# Feedback Record

Copy this file before any work starts, including work that is expected to happen immediately. Keep one record per feedback item. This is a source-only workflow record, not a Claim, Authority Reference, Memory entry, Bundle, or projection.

## Control Fields

```yaml
feedback_id: feedback_<stable-id>
source: <person, project, session, or document>
affected_system: <system or project>
processing_state: received
validation_state: none
promotion_decision: not_promoted
```

Allowed `processing_state` values are `received`, `in_progress`, `blocked`,
`deferred`, and `rejected`. Allowed `validation_state` values are `none`,
`local_passed`, `user_pending`, and `production_passed`.

Create the record with `processing_state: received` before interpreting or
acting on the feedback. Change the state only when the record is updated.
`deferred` and `rejected` require a reason in the outcome section.

## Original Feedback

Record the original input separately and preserve it verbatim. Do not replace
or rewrite it when adding interpretation, actions, or validation. Corrections
or clarifications are appended as dated notes.

- Reported at: `<date/time>`
- Original source link or reference: `<path, URL, or session ID>`
- User intent: `<what the user wants changed, checked, or understood>`

> Paste the original feedback here, unchanged.
>
> <original feedback>

## Interpretation

This section is the working interpretation. It is not part of the original
feedback and must not be presented as a confirmed project fact.

- Observation: `<what was observed>`
- Scope: `<affected system/project and boundary>`
- Suggested change: `<suggestion, or none>`
- Open questions: `<unknowns, or none>`

## Work Items

Track each action independently. Keep completed and remaining work visible;
do not delete an item when it is deferred, blocked, or rejected.

| ID | Work item | Status | Evidence or reason |
| --- | --- | --- | --- |
| W1 | `<bounded action>` | `remaining` | `<link, result, or reason>` |

Use `completed`, `remaining`, `deferred`, or `rejected` for work-item status.
A `deferred` or `rejected` item must include its reason in the table.

## Validation And Outcome

- Completed evidence: `<tests, review, or other evidence; none if not started>`
- Remaining work: `<what is still required, or none>`
- Validation note: `<what the validation does and does not prove>`
- Artifact links: `<paths or links, or none>`
- Outcome reason: `<required for blocked, deferred, or rejected processing>`

`local_passed` means only that the local check passed. It does not close work
that still needs user or production validation: keep `processing_state` as
`in_progress` and use `validation_state: user_pending` or leave the required
production work visible in `Remaining work`. Use `production_passed` only when
that production validation has actually occurred.

## Closeout Checklist

Before recording a final outcome, confirm each applicable item:

- [ ] Every work item has a status; completed, remaining, deferred, and rejected work is visible.
- [ ] Remaining work is `none` only when no further action or required validation is outstanding.
- [ ] `local_passed` is not treated as user or production validation; pending validation remains visible.
- [ ] Deferred, blocked, and rejected work has a reason and a next action or explicit stop.
- [ ] Completed evidence and artifact links are recorded, with their limits stated.
- [ ] `promotion_decision` remains `not_promoted` unless a separate explicit governed workflow was requested and completed.
- [ ] No Claim, Authority Ref, Memory, Bundle, projection, or Git state was changed by this record.

Do not mark the feedback complete while any required checklist item is
unchecked. A checklist is a review aid, not automatic closeout or permission
to mutate project knowledge.

## Promotion Decision

- Decision: `not_promoted`
- Reason: `<feedback remains a workflow record; state the evidence and review needed for any future promotion>`
- Related Claim, Authority Ref, Memory, or Bundle: `none`

Do not automatically convert feedback into a Claim or alter Claim, Authority
Ref, Memory, Bundle, projection, or Git state. Any future promotion requires a
separate explicit request and the governed workflow of the owning project.

## Handoff And References

If this record is handed to another agent, state the next session's main task
before listing deeper references. A matching handoff should use its recovery
package without re-reading original references. Read an original reference
only for a named missing fact or bounded evidence gap, and state that reason.

- Next task: `<one sentence, or none>`
- Targeted reference read reason: `<reason, or none>`
- References: `<paths or links, with purpose>`
