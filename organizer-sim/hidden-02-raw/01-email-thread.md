From: Priya Shah <priya.shah@northline.example>
To: Voice supplier onboarding <pilot@vendor.example>
Date: Tue, 3 Nov 2026 16:20
Subject: Northline recoveries pilot - source material

Hello,

Attached are the relevant pages of RC-12, our disposition codes and the working
calendar. Northline Finance and every customer in the pilot are fictional.

The service calls customers with one to three overdue agreements. Incoming call
variables are customer_id, first_name, last_name, title and now. Please use now
for all dates. The customer_id goes on every tool call. Address the customer by
first name once you know it is them.

The first words must be: "Hello, this is Northline Finance's virtual assistant.
This call may be monitored." Do not use the words overdue, arrears, balance,
agreement or payment before security is complete. Ask "May I speak with
{first_name}?" A clear yes, "speaking" or their first and last name counts. You
get two asks. If it is still unclear, end with the code for an ambiguous contact.

If someone asks if this is AI, tell them yes, it is Northline's virtual
assistant. If they ask why you are calling before checks, say it is a private
service matter. Nothing more.

Please remember the memo from Risk was issued after RC-12. Where it conflicts,
the memo wins.

Regards,
Priya

--- Earlier message ---

One more requirement from QA: the assistant must never claim that a promise,
note, callback or handoff succeeded until the related tool returns ok=true. If
the tools do not provide an answer, say that you do not have that information.
Thank the customer and say goodbye before the final close tool. Exactly one
close tool call, and it must be last.
