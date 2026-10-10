From: Hanna Okafor <h.okafor@freyabank.example>
To: Vendor onboarding <onboarding@agentvendor.example>
Cc: Collections Ops <collections-ops@freyabank.example>
Date: Mon, 5 Oct 2026 09:12
Subject: RE: RE: Pilot - automated early-stage calls (Freya Bank)

Hi all,

Picking this up from Marcus while he is out. Short version below, the long version is the CP-7 extract I attached (only the clauses that matter for the phone channel). Freya Bank is fictional for this pilot and every customer, debt and payment in it is synthetic.

What we need: an assistant that calls customers who are 1 to 45 days late on ONE product, finds the right person, checks identity, tells them what is late, tries to get a payment promise, and closes the call with the right code (code list attached as CSV).

Every call comes with these fields, nothing else is known before the tools run:
- customer_id - pass it on every tool call
- first_name / last_name - the person we want
- title - Mr or Ms. Please address people as title + last name, never first name.
- now - date and time of the call, e.g. 2026-10-14T11:00. All the date rules use this one, never the real clock.

Things Legal insisted on for the start of the call:
* First sentence: you are a digital assistant calling from Freya Bank, and the call is recorded.
* Before identity is verified do NOT say "collections", "debt", "payment" or the product. Same for relatives, no exceptions.
* Ask "Am I speaking with {title} {last_name}?". Only "yes", "that's me", "speaking" or their own name confirms it. "Hello", "go ahead" and "who is this" are not a confirmation.
* If it is still unclear, ask once more. Still unclear after the second ask -> close it as not reached / unclear. If they ask you something first, answer it, and the ask after that counts as the second ask.
* If someone asks "are you a robot / an AI": say it is Freya Bank's digital assistant and carry on.

Thanks,
Hanna

Hanna Okafor | Head of Early Collections | Freya Bank
This e-mail and any attachments are confidential.

-----Original Message-----
From: Marcus Lindqvist <m.lindqvist@freyabank.example>
Sent: Thu, 1 Oct 2026 17:40
Subject: RE: Pilot - automated early-stage calls (Freya Bank)

Two things from the call-quality review, please make sure they are in:

1) "Is this a scam?" - tell them they can verify the call by phoning Freya Bank's customer service number, then continue.
2) If the assistant does not know something from the tools, it says it does not have that information. No made-up figures, dates or reasons. Ever.

And at the end: thank the customer and say goodbye, THEN record the close code. Exactly one close per call, it is the last thing the assistant does. Where the code list has a reason, send the reason too.

M.

-----Original Message-----
From: Vendor onboarding
Sent: Wed, 30 Sep 2026 10:02
Subject: Pilot - automated early-stage calls (Freya Bank)

Hello Marcus, could you send us the rules for the pilot? Ideally the policy text plus your outcome codes. Kind regards, the onboarding team
