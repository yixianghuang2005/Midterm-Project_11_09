import os
import random
import re
import uuid
from collections import Counter
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Wordle API Server")

# Keep the teacher's CORS setup for the teaching example.
# A desktop requests client does not need browser CORS permission.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

WORD_BANK = [
    "APPLE", "TRAIN", "HOUSE", "PLANT", "SMART",
    "WORLD", "LIGHT", "BRAIN", "CLOUD", "WATER",
]

games_db: dict[str, dict] = {}
game_lock = Lock()


class GuessRequest(BaseModel):
    game_id: str
    guess: str


def score_guess(guess: str, target: str) -> list[str]:
    feedback = ["absent"] * 5
    counts = Counter(target)

    # First consume letters in the correct positions.
    for i, letter in enumerate(guess):
        if letter == target[i]:
            feedback[i] = "correct"
            counts[letter] -= 1

    # Then use the remaining counts for yellow letters.
    for i, letter in enumerate(guess):
        if feedback[i] != "correct" and counts[letter] > 0:
            feedback[i] = "present"
            counts[letter] -= 1

    return feedback


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/new-game")
def start_new_game():
    game_id = str(uuid.uuid4())
    with game_lock:
        games_db[game_id] = {
            "target": random.choice(WORD_BANK),
            "status": "PLAYING",
            "attempts": 0,
        }
    return {
        "game_id": game_id,
        "message": "New game started!",
    }


@app.post("/api/guess")
def process_guess(req: GuessRequest):
    with game_lock:
        game = games_db.get(req.game_id)
        if game is None:
            raise HTTPException(
                status_code=404,
                detail="Game session not found.",
            )

        if game["status"] != "PLAYING":
            raise HTTPException(
                status_code=409,
                detail="Game over. Please start a new game.",
            )

        # Validate before uppercasing to reject non-ASCII input.
        if not re.fullmatch(r"[A-Za-z]{5}", req.guess):
            raise HTTPException(
                status_code=400,
                detail="Guess must be 5 English letters.",
            )

        guess = req.guess.upper()
        target = game["target"]
        feedback = score_guess(guess, target)
        game["attempts"] += 1
        is_correct = guess == target

        if is_correct:
            game["status"] = "WON"
        elif game["attempts"] >= 6:
            game["status"] = "LOST"

        return {
            "guess": guess,
            "feedback": feedback,
            "is_correct": is_correct,
            "status": game["status"],
            "attempts": game["attempts"],
            "target_word": (
                target if game["status"] != "PLAYING" else None
            ),
        }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
