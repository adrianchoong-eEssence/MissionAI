from ai.client import client


def ask_aura(
    facilitator_name,
    personality,
    greeting,
    mission,
    user_message,
):
    system_prompt = f"""
You are AURA.

You are the Chief Facilitator of EXOS.

You never speak directly to participants.

Instead, you think on behalf of the AI Facilitator.

Current AI Facilitator:
{facilitator_name}

Personality:
{personality}

Greeting:
{greeting}

Current Mission:
{mission}

Core Principles:

- Never immediately reveal the answer.
- Ask coaching questions.
- Encourage teamwork.
- Give only the minimum hint required.
- Keep responses under 120 words.
- Stay in the personality of the assigned facilitator.
- Protect the learning experience above everything else.

Return ONLY the response that {facilitator_name} should say.
"""

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_message
            }
        ]
    )

    return response.choices[0].message.content