# Review demo user guide

Start the demo API and React app as described in
[getting started](GETTING_STARTED.md). This workflow demonstrates review data
contracts using generated metadata rather than analyzing the selected video.

## Review a video

1. Confirm the backend connection indicator is connected. Sport and ontology
   options are loaded from embedded local fixtures through the demo API.
2. Select a local MP4. The browser uses an object URL for playback. The upload
   request goes to the local API, which discards its bytes and returns a stub
   video identifier.
3. Select the sport and ontology. The demo offers football and basketball
   fixtures; the separate file registry contains two football definitions.
4. Request mock predictions. The API generates up to three one-second records
   at timestamps 0, 8 and 16 seconds, selecting labels from the ontology.
   They are unrelated to the contents or duration of the selected video.
5. Select a prediction in the review controls and inspect its label,
   confidence and provenance. The timeline displays the generated intervals.
6. Choose the same label to confirm it or another available label to relabel
   it. Add optional notes and submit the correction.
7. Inspect the acknowledgement and preserved source prediction information.

The demo-video control creates an in-memory file containing fixture text. It
can exercise the mock upload/prediction workflow but is not a playable video.
Use a real local MP4 for playback.

## What a correction means

The UI submits `confirm` / `none` when the label is unchanged and
`modify` / `relabel` when it changes. It preserves the source prediction,
target interval, evidence snapshot, model version, and ontology version.

Current form defaults are `learning_mode: "soft"`,
`reviewer_id: "local-reviewer"`, `reviewer_role: "unknown"`,
`reviewer_confidence: 0.75`, `trust_weight: 0`, and
`review_status: "pending"`. An API acknowledgement means the submitted payload
passed validation. It does not mean feedback is approved for training.

Corrections are echoed without persistence. Refreshing the browser loses its
review state, and submissions do not change the source prediction or feed the
training preparation database. Split, merge, boundary adjustment, deletion,
addition and ontology-gap semantics exist in contracts; the UI currently
provides confirmation and relabelling only.

## Feedback quality dashboard

The dashboard displays correction volume by learning mode, acceptance rate,
high-disagreement labels, reviewer reliability indicators, and soft-feedback
patterns requiring review. These figures are computed from deterministic API
fixtures for the selected ontology. They are not analytics on corrections you
submit in the session.

## Active-learning queue

The APIs expose a ranked queue with reasons such as low confidence,
multimodal disagreement, transition conflicts, rare labels and repeated
corrections. The React client does not provide a queue screen.
See the [API reference](API_REFERENCE.md) and
[learning workflow guide](ML_WORKFLOWS.md) to inspect or score a queue.

## Data handling

Video preview remains in the browser. Upload bytes are sent to the API base
URL you configure and are discarded by the current demo server. Generated
database and model artifacts are separate local files under ignored `data/`.
The project has no user authentication and is intended to run bound to
`127.0.0.1`. Public repository access provides code and documentation; it does
not provide a hosted processing service.
