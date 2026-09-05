# Retention Action Agent

## Inspiration

I'd already built something similar — a churn-risk dashboard for
freelance consultants. It worked fine, but it had one obvious problem:
it would tell you a client was at risk and then just... stop.
Everything after that was on me. And realistically, that's exactly the
moment a busy consultant doesn't have time to act.

When this hackathon asked for an agent that actually does the work
instead of just talking about it, that gap felt like the natural place
to start.

## What it does

It looks at a client's situation — risk score, how long since you last
talked, any notes you've left — and figures out if something needs to
happen. If it does, it decides what: a check-in message, a call, or
nothing at all. It drafts the message itself, in your voice.

Then it makes one more call: is it sure enough to just send this, or
should you look at it first? Above a confidence threshold you set, it
sends. Below it, it lands in your review inbox instead. That split
isn't up to the model, on purpose — the code enforces it, so a human's
always in the loop for anything genuinely unclear.

The dashboard lets you add clients, run the agent, see what it's done,
review flagged decisions, tweak the threshold, plus a support form and
privacy page so it doesn't feel like a half-finished demo.

## How I built it

Python and the Strands Agents SDK for the agent itself — two tools
(pull client context, record the decision) and a system prompt that
tells it to stay cautious on anything touching a complaint or a
payment dispute.

I didn't lock it to one model provider. It runs on Anthropic, Groq, or
Bedrock with basically a one-line swap. That wasn't originally the
plan — more on that below.

Supabase for data, with row-level security turned on for every table.
The dashboard's key can only do what it's supposed to; the agent
writes through a separate, more privileged key that never touches a
browser.

The dashboard's React, Vite, and Tailwind. There's a small Flask API
sitting between the dashboard and the agent — and that's not a
throwaway piece, it's literally the same function an AWS Lambda would
call once this is deployed.

It also has a daily call cap, so it can't rack up cost if something
goes wrong, and it won't review the same client twice within 12 hours
for no reason.

## Challenges I ran into

Honestly? My AWS account still hasn't cleared phone verification.
I've got a support case open and I've tried more or less everything.
Rather than let that stall the whole project, I built the model layer
to be swappable from the start — so when Bedrock wasn't reachable,
switching to Groq's free tier took minutes, not a rewrite.

Outside of that, it was a lot of small, very normal dev friction —
a PowerShell permissions issue, a wrong Supabase URL causing CORS
errors, a model ID that got deprecated by the provider mid-build.
None of it was hard exactly, just the usual tax of actually shipping
something instead of just planning it.

## Accomplishments I'm proud of

The agent's decisions are real, not scripted. It's chosen to escalate
to a phone call instead of just sending another message when the
situation actually called for that — which is a genuinely useful,
non-obvious call for it to make on its own.

I also didn't leave security for later. Row-level security and
separating the two keys happened before the product was "done," not
patched in afterward because a checklist told me to.

## What I learned

The hard part of building an agent isn't the model call — it's
deciding what the model gets to decide, versus what stays in plain
code you can actually audit. The confidence threshold is the clearest
example of that: let the model reason and draft, but never let it be
the one deciding it's safe to act alone.

## What's next

Deploy to Lambda (or AgentCore) once my AWS account actually works.
Wire up real message sending — right now it logs what it would send,
on purpose, since I didn't want to risk emailing a real person while
still debugging.

## Built with
Python, Strands Agents SDK, React, Vite, Tailwind CSS, Supabase,
Flask, Anthropic API, Groq API