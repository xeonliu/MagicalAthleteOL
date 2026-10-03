"""Two independent WebSocket players complete all four races through public intents."""
import random
from collections import Counter

from fastapi.testclient import TestClient

from magical_athlete import main
from magical_athlete import rooms as room_module
from magical_athlete.game import MagsimGameEngine


def test_two_players_complete_four_races(monkeypatch):
    repository = room_module.InMemoryRoomRepository()
    monkeypatch.setattr(main, "repository", repository)
    monkeypatch.setattr(main, "rooms", room_module.RoomManager(repository, local_timers=False))
    monkeypatch.setattr(room_module, "MagsimGameEngine", lambda: MagsimGameEngine(random.Random(17)))
    monkeypatch.setattr(room_module, "ROLL_ANIMATION_LEAD_SECONDS", 0)
    headers = {"origin": "http://localhost:5173"}
    with TestClient(main.app) as client:
        room_id = client.post("/api/rooms").json()["roomId"]
        with client.websocket_connect("/ws", headers=headers) as a, client.websocket_connect("/ws", headers=headers) as b:
            a.send_json({"type": "JOIN_ROOM", "roomId": room_id, "playerName": "测试小明"})
            first = a.receive_json()
            b.send_json({"type": "JOIN_ROOM", "roomId": room_id, "playerName": "测试小红"})
            second = b.receive_json()
            a.receive_json()
            sockets = {first["playerId"]: a, second["playerId"]: b}
            host = first["playerId"]
            game = second["game"]
            events = Counter()
            completed_races = set()
            actions = Counter()
            choices = Counter()
            trip_sources = Counter()
            decision_log = Counter()
            for step in range(1500):
                phase = game["phase"]
                actor = host
                if phase == "FINISHED":
                    completed_races.add(game["raceNumber"])
                    break
                if phase == "LOBBY":
                    intent = {"type": "START_GAME"}
                elif phase in {"DRAFT_ROLL", "RACE_ROLL"}:
                    actor = next(p["id"] for p in game["players"] if p["id"] in game["rollCandidateIds"] and not p["rollValues"])
                    intent = {"type": "ROLL_START"}
                elif phase == "DRAFTING":
                    actor = game["activePlayerId"]
                    intent = {"type": "DRAFT_ATHLETE", "athleteId": game["draftPool"][0]["id"]}
                elif phase == "CHARACTER_SELECTION":
                    player = next(p for p in game["players"] if not p["selectionLocked"])
                    actor = player["id"]
                    available = [c["id"] for c in player["team"] if c["id"] not in player["usedAthleteIds"]]
                    intent = {"type": "SELECT_RACERS", "athleteIds": available[:game["selectionCount"]]}
                elif phase == "RACE_RESULTS":
                    completed_races.add(game["raceNumber"])
                    intent = {"type": "ADVANCE_RACE"}
                elif game["pendingDecision"]:
                    choice = game["pendingDecision"]
                    choices[choice["abilityName"]] += 1
                    actor = choice["playerId"]
                    options = choice["options"]
                    selected = next((o for o in options if o["id"] == "skip"), options[-1])
                    intent = {"type": "RESOLVE_DECISION", "decisionId": choice["id"], "optionId": selected["id"]}
                else:
                    actor = game["pendingRoll"]["nextPlayerId"] if game["pendingRoll"] else game["activePlayerId"]
                    intent = {"type": "ROLL_DICE"}
                intent["actionId"] = f"full-match-{step}"
                actions[intent["type"]] += 1
                sockets[actor].send_json(intent)
                updates = []
                for socket in (sockets[actor], sockets[next(p for p in sockets if p != actor)]):
                    while True:
                        message = socket.receive_json()
                        assert message["type"] != "ERROR", message
                        if message["type"] == "STATE_UPDATED":
                            updates.append(message)
                            break
                assert updates[0]["revision"] == updates[1]["revision"]
                for field in ("phase", "activePlayerId", "raceNumber", "raceResults", "winnerIds"):
                    assert updates[0]["game"][field] == updates[1]["game"][field]
                assert [(p["id"], p["score"], p["activeRacers"]) for p in updates[0]["game"]["players"]] == [(p["id"], p["score"], p["activeRacers"]) for p in updates[1]["game"]["players"]]
                game = updates[0]["game"]
                events.update(e["type"] for e in updates[0]["events"])
                for logged in game["raceLog"]:
                    if logged["type"] == "RACER_TRIPPED":
                        trip_sources[logged.get("source")] += 1
                    if logged["type"] == "DECISION_RESOLVED":
                        decision_log[logged.get("optionLabel") or "-"] += 1
            assert game["phase"] == "FINISHED", (game["phase"], actions, choices, game["pendingDecision"])
            assert completed_races == {1, 2, 3, 4}
            assert game["winnerIds"]
            assert all(len(p["usedAthleteIds"]) == 8 for p in game["players"])
            assert events["ABILITY_TRIGGERED"] > 0
            assert actions["RESOLVE_DECISION"] > 0
            # Board tiles trip racers too, and every skill choice has to stay readable.
            assert trip_sources["TripTile"] > 0, trip_sources
            assert "-" not in decision_log, decision_log
            print({"actions": dict(actions), "races": sorted(completed_races), "trips": dict(trip_sources), "choices": dict(decision_log), "scores": [(p["name"], p["score"]) for p in game["players"]], "skills": events["ABILITY_TRIGGERED"]})
