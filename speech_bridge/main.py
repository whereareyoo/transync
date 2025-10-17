from fastapi import FastAPI

app = FastAPI(title="Speech Bridge", version="0.1")

@app.get("/health")
def health():
    return {"status": "ok"}
if __name__ == '__main__':
    print_hi('PyCharm')

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
