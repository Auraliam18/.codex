"""Launch the Aura Trade Panel: python run.py"""

import uvicorn

if __name__ == "__main__":
    print("\n  ⚡ Aura Trade Panel → http://127.0.0.1:8420\n")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8420, reload=False)
