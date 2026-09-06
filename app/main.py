import os
import pathlib
from fastapi.responses import HTMLResponse

from app.harness.tracing import init_tracing
init_tracing()

from app.api.app import app

UI_PATH = pathlib.Path(__file__).parent.parent / 'ui' / 'index.html'

@app.get('/', response_class=HTMLResponse)
def index():
    if UI_PATH.exists():
        return UI_PATH.read_text(encoding='utf-8')
    return (
        '<html><head><title>ReconcileOS API</title></head>'
        '<body><h1>ReconcileOS API is running</h1>'
        '<p><a href="/docs">Docs</a></p></body></html>'
    )

__all__ = ['app']

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000)
