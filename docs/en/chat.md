# Using the Chat

[日本語](../ja/chat.md) | **English** ・ [← README](../../README.en.md)

The decision chat lets you give Laya some text and questions and see how it decides, right in the browser.
Laya does not generate text. It is a decision model that answers the questions you give it — yes/no, one of several options, or which level on a scale — with probabilities. So the chat works the same way: you send a piece of text (the state), and you get answers to the questions you prepared.

![The decision chat](../images/chat-en.png)

## Opening it

1. Start the containers as described in [Deploying the Docker containers](deploy.md). The chat only starts when `.env` contains `COMPOSE_PROFILES=dev` (the default in `.env.example`).
2. Open <http://127.0.0.1:22301> in a browser.

The chat signs API requests on the server side, so the secret key never reaches the browser.
On the other hand, anyone who can reach the chat can use the API, so the chat is published only on `127.0.0.1`.

## Screen layout

| Area | Contents |
|---|---|
| Status at the top right | Laya's state. `Laya ready ・ cpu ・ english, multilingual` means english and multilingual are loaded on CPU |
| Button at the top right | Switches the display language (日本語 / English). The first time, it follows the browser's language |
| Left | The conversation log and the box for the text to judge |
| Right | Model selection, question editor, metadata |

## Basic flow

1. Set up questions in the right panel (three examples are there to start with).
2. Type the text you want judged in the box at the bottom.
3. Press "Send" (or Ctrl+Enter).
4. You get an answer and probabilities for each question.

## Writing questions

Add a question with "＋ noul", "＋ choice" or "＋ score", and remove one with ×. Each question has three fields.

| Field | Contents |
|---|---|
| Question ID | The name shown as the heading of the result. Up to 64 letters, digits, `_`, `.`, `-`. Must be unique |
| instructions | What to decide, in plain language (e.g. "Does this need a response today?") |
| criteria | The possible answers. How to write them depends on the type (below) |

| Type | Answers | How to write criteria | Example |
|---|---|---|---|
| noul | Yes / no | Optional. Line 1 is the meaning of true, line 2 the meaning of false | `A same-day reply is needed`<br>`The normal queue is fine` |
| choice | One of several options | One "label: description" per line (2–100). Without a description, the label is used as the description | `returns: Returns or damaged items`<br>`delivery: Delivery status` |
| score | A level on a scale | One label per line, from low to high (2–32) | `Routine`<br>`Soon`<br>`Today` |

"Reset questions to defaults" brings back the examples.

## Writing the text (state)

The text you type becomes Laya's `state` as is.
If you type valid JSON starting with `{` or `[`, it is sent as JSON rather than a string (useful for judging structured data).

## Choosing a model

| Option | Meaning |
|---|---|
| Auto (route by language) | Laya looks at the language of the text and picks english or multilingual. Usually this is what you want |
| english | The English checkpoint (based on ModernBERT-large) |
| multilingual | A checkpoint for 100+ languages (based on mmBERT-base). Use this for Japanese and other non-English text |
| typed-decisions | A checkpoint fine-tuned on four fixed workflows (customer service, invoice processing, security incidents, agent trace observability). Never chosen automatically. Not loaded at startup by default, so the first use is slow while it downloads and loads |

## Reading the results

| Type | What is shown | How to read it |
|---|---|---|
| noul | "Yes" or "No", and P(true) | "Yes" when the probability of true is 50% or more |
| choice | The most likely option and its confidence | The bars show each option's probability |
| score | The most likely level, score and confidence | score is the expected level number (0-based). E.g. 2.27 on a 4-level scale leans to the third level (Today) |

The line under each answer shows the model that was used (e.g. `model: english`), the round-trip time, input/output tokens and Laya's inference time.
Open "Raw JSON" to see the API response as is.

## Metadata

Open "Metadata (optional)" to enter `session_id` and `user`. The values are added to the request and passed to Laya unchanged.

## What is saved

Questions, model, metadata and display language are saved in the browser (localStorage) and survive a reload. The conversation log is not saved.

## When something goes wrong

| What you see | Cause |
|---|---|
| A red message before sending | A question is not written correctly (duplicate ID, only one choice option, etc.). Fix it as the message says |
| `Error 413` | A limit was exceeded (too many questions, text too long, etc.). See the limits in [Using the API](api.md#6-status-codes-and-limits) |
| `Error 422` | Laya rejected the question format. The reason is in `detail` in the raw JSON |
| `Error 502` / "Cannot reach Laya" at the top right | Laya is still starting. Wait a while |
| `Error 503` | Too many requests at once. Wait a moment and send again |
