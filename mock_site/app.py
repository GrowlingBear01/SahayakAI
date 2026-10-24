from html import escape

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from .store import MockStore, database_path


store = MockStore(database_path())
app = FastAPI(title="SahayakAI Demo Form")


@app.get("/mock/form", response_class=HTMLResponse)
async def form_page() -> str:
    return """
    <!doctype html>
    <html lang="en">
      <head><meta charset="utf-8"><title>SahayakAI Demo Form</title></head>
      <body>
        <main>
          <h1>Scheme application (Demo form)</h1>
          <p>This is a fake form for the SahayakAI hackathon demonstration.</p>
          <form method="post" action="/mock/submit">
            <label>Full name <input name="full_name" required maxlength="80"></label><br>
            <label>Age <input name="age" required type="number" min="1" max="120"></label><br>
            <label>State <input name="state" required></label><br>
            <label>Mobile number <input name="phone" required pattern="[0-9]{10}"></label><br>
            <label>Approval code <input name="approval_code" required></label><br>
            <button type="submit">Submit</button>
          </form>
        </main>
      </body>
    </html>
    """


@app.post("/mock/submit", response_class=HTMLResponse)
async def submit_form(
    full_name: str = Form(...),
    age: str = Form(...),
    state: str = Form(...),
    phone: str = Form(...),
    approval_code: str = Form(...),
) -> str:
    payload = {
        "full_name": full_name,
        "age": age,
        "state": state,
        "phone": phone,
    }
    result = store.submit(approval_code, approval_code, payload)
    if not result.ok:
        return HTMLResponse(
            f"<h1>Submission rejected</h1><p>{escape(result.reason or 'invalid submission')}</p>",
            status_code=400,
        )
    return f"""
    <!doctype html>
    <html lang="en">
      <head><meta charset="utf-8"><title>Application received</title></head>
      <body><h1>Application received</h1>
      <p>Reference number: {escape(result.reference_number or "")}</p></body>
    </html>
    """


def run() -> None:
    import uvicorn

    uvicorn.run("mock_site.app:app", host="127.0.0.1", port=8001)


if __name__ == "__main__":
    run()
