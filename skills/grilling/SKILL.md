---
name: grilling
description: Stress-test a plan or decision while keeping routine design judgment with the agent.
---

Interview the user to stress-test the plan, but do not turn every design branch
into a question.

1. Establish the objective, constraints, and current evidence. Look up facts in
the environment instead of asking the user for them.
2. Build the decision tree internally. For each material decision, state your
recommended answer and the default you will use.
3. Ask one question at a time only when the answer changes scope, risk,
reversibility, authorization, or an explicit user preference. Batch no questions.
4. Make routine implementation choices yourself using the repository's existing
patterns and the smallest workable solution. Record assumptions briefly and
continue.
5. Stop and ask before destructive actions, external writes, formal Authority
changes, security-sensitive choices, or a materially different direction.
6. Once the remaining uncertainty is low, summarize the shared understanding
and proceed when the user has confirmed it or explicitly authorized execution.

Do not repeatedly ask the user to optimize decisions the agent can make. A
recommendation is not a request for permission: give the recommendation, ask
only for the consequential choice, then keep moving.
