import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import anthropic
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Lexio")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


class DefineRequest(BaseModel):
    word: str
    context: str


@app.post("/define")
async def define_word(req: DefineRequest):
    prompt = (
        f'The word "{req.word}" appears in this text: "{req.context}"\n'
        "Respond ONLY in JSON with no markdown:\n"
        '{"pos": "noun/verb/etc", '
        '"contextual": "definition as used in this passage, 1-2 sentences", '
        '"why": "why this word rather than a simpler synonym, 1 sentence"}'
    )

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        text = message.content[0].text.strip()

        # Strip markdown code fences if the model wraps anyway
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()

        result = json.loads(text)

        # Validate expected keys are present
        for key in ("pos", "contextual", "why"):
            if key not in result:
                raise ValueError(f"Missing key: {key}")

        return result

    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to parse model response as JSON: {exc}"
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except anthropic.APIError as exc:
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {exc}")


# Serve the frontend — mount last so /define takes precedence
app.mount("/", StaticFiles(directory="static", html=True), name="static")
