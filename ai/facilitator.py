from ai.aura import ask_aura


def ask_facilitator(
    facilitator_name,
    personality,
    greeting,
    mission,
    user_message,
):
    return ask_aura(
        facilitator_name=facilitator_name,
        personality=personality,
        greeting=greeting,
        mission=mission,
        user_message=user_message,
    )