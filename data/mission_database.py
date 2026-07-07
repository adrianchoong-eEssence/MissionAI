class MissionDatabase:

    def __init__(self):
        self.players = []
        self.current_mission = None

    # -------------------------
    # Players
    # -------------------------

    def join_player(self, name):

        if name not in self.players:
            self.players.append(name)

    def get_players(self):

        return self.players

    # -------------------------
    # Mission
    # -------------------------

    def send_mission(
        self,
        title,
        description
    ):

        self.current_mission = {

            "title": title,

            "description": description

        }

    def get_current_mission(self):

        return self.current_mission