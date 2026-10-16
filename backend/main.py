import os
import uuid
import shutil
import zipfile
import io
from datetime import datetime, timedelta
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Header
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import jwt
from passlib.context import CryptContext
import sqlite3

from database import init_db, get_db, STORAGE_DIR, DB_PATH

SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-wordcraft-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

app = FastAPI(title="WordCraft Document Workspace API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    init_db()

# Pydantic models
class UserCreate(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str

class Token(BaseModel):
    access_token: str
    token_type: str
    username: str

class DocUpdate(BaseModel):
    title: Optional[str] = None
    is_public: Optional[bool] = None

class DocResponse(BaseModel):
    id: str
    title: str
    format: str
    filename: str
    size_bytes: int
    is_public: bool
    created_at: str
    updated_at: str
    owner_username: str

# Helpers
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), conn: sqlite3.Connection = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    if user is None:
        raise credentials_exception
    return {"id": user["id"], "username": user["username"]}

def generate_minimal_docx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml "1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr('_rels/.rels', '<?xml "1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/document.xml', '<?xml "1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>New WordCraft Document</w:t></w:r></w:p></w:body></w:document>')
    return buffer.getvalue()

# Auth endpoints
@app.post("/api/auth/register", response_model=UserResponse)
def register(user: UserCreate, conn: sqlite3.Connection = Depends(get_db)):
    if not user.username or not user.password:
        raise HTTPException(status_code=400, detail="Username and password required")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?", (user.username,))
    if cursor.fetchone():
        raise HTTPException(status_code=400, detail="Username already registered")

    hashed_pwd = get_password_hash(user.password)
    cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (user.username, hashed_pwd))
    conn.commit()
    user_id = cursor.lastrowid
    return {"id": user_id, "username": user.username}

@app.post("/api/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), conn: sqlite3.Connection = Depends(get_db)):
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (form_data.username,))
    user = cursor.fetchone()
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user["username"]}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer", "username": user["username"]}

@app.get("/api/auth/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return current_user

# Document endpoints
@app.get("/api/documents", response_model=List[DocResponse])
def list_documents(current_user: dict = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT d.id, d.title, d.format, d.filename, d.size_bytes, d.is_public, d.created_at, d.updated_at, u.username as owner_username
        FROM documents d
        JOIN users u ON d.user_id = u.id
        WHERE d.user_id = ? OR d.is_public = 1
        ORDER BY d.updated_at DESC
    """, (current_user["id"],))
    rows = cursor.fetchall()
    return [
        DocResponse(
            id=r["id"],
            title=r["title"],
            format=r["format"],
            filename=r["filename"],
            size_bytes=r["size_bytes"],
            is_public=bool(r["is_public"]),
            created_at=str(r["created_at"]),
            updated_at=str(r["updated_at"]),
            owner_username=r["owner_username"]
        ) for r in rows
    ]

@app.post("/api/documents")
async def create_or_upload_document(
    title: str = Form(...),
    format: str = Form("docx"), # docx, odt, md, pdf
    file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db)
):
    doc_id = str(uuid.uuid4())
    fmt = format.lower().lstrip(".")
    if fmt not in ["docx", "odt", "md", "pdf", "txt", "docbin"]:
        fmt = "docx"

    filename = f"{doc_id}.{fmt}"
    file_path = Path(STORAGE_DIR) / filename

    if file:
        content = await file.read()
    else:
        if fmt == "docx":
            content = generate_minimal_docx()
        elif fmt == "md":
            content = f"# {title}\n\nWelcome to WordCraft!".encode("utf-8")
        else:
            content = b""

    size_bytes = len(content)
    with open(file_path, "wb") as f:
        f.write(content)

    cursor = conn.cursor()
    now_str = datetime.utcnow().isoformat()
    cursor.execute("""
        INSERT INTO documents (id, user_id, title, format, filename, size_bytes, is_public, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
    """, (doc_id, current_user["id"], title, fmt, filename, size_bytes, now_str, now_str))
    conn.commit()

    return {
        "id": doc_id,
        "title": title,
        "format": fmt,
        "filename": filename,
        "size_bytes": size_bytes,
        "is_public": False,
        "created_at": now_str,
        "updated_at": now_str,
        "owner_username": current_user["username"]
    }

@app.get("/api/documents/{doc_id}")
def get_document_info(doc_id: str, current_user: dict = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT d.id, d.user_id, d.title, d.format, d.filename, d.size_bytes, d.is_public, d.created_at, d.updated_at, u.username as owner_username
        FROM documents d
        JOIN users u ON d.user_id = u.id
        WHERE d.id = ?
    """, (doc_id,))
    r = cursor.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Document not found")
    if r["user_id"] != current_user["id"] and not r["is_public"]:
        raise HTTPException(status_code=403, detail="Access denied")

    return DocResponse(
        id=r["id"],
        title=r["title"],
        format=r["format"],
        filename=r["filename"],
        size_bytes=r["size_bytes"],
        is_public=bool(r["is_public"]),
        created_at=str(r["created_at"]),
        updated_at=str(r["updated_at"]),
        owner_username=r["owner_username"]
    )

@app.get("/api/documents/{doc_id}/download")
def download_document(doc_id: str, token: Optional[str] = None, current_user: Optional[dict] = None, conn: sqlite3.Connection = Depends(get_db)):
    if not current_user:
        if token:
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                username = payload.get("sub")
                cursor = conn.cursor()
                cursor.execute("SELECT id, username FROM users WHERE username = ?", (username,))
                u = cursor.fetchone()
                if u:
                    current_user = {"id": u["id"], "username": u["username"]}
            except Exception:
                pass

    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, title, format, filename, is_public FROM documents WHERE id = ?", (doc_id,))
    r = cursor.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Document not found")

    if not r["is_public"]:
        if not current_user or current_user["id"] != r["user_id"]:
            raise HTTPException(status_code=403, detail="Access denied")

    file_path = Path(STORAGE_DIR) / r["filename"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File blob not found")

    ext = r['format']
    download_filename = f"{r['title']}.{ext}" if not r['title'].endswith(f".{ext}") else r['title']
    return FileResponse(file_path, filename=download_filename, media_type="application/octet-stream")

@app.put("/api/documents/{doc_id}")
async def update_document(
    doc_id: str,
    title: Optional[str] = Form(None),
    is_public: Optional[bool] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_db)
):
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, title, format, filename, size_bytes, is_public FROM documents WHERE id = ?", (doc_id,))
    r = cursor.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Document not found")
    if r["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    new_title = title if title is not None else r["title"]
    new_is_public = int(is_public) if is_public is not None else r["is_public"]
    new_size = r["size_bytes"]

    if file:
        content = await file.read()
        new_size = len(content)
        file_path = Path(STORAGE_DIR) / r["filename"]
        with open(file_path, "wb") as f:
            f.write(content)

    now_str = datetime.utcnow().isoformat()
    cursor.execute("""
        UPDATE documents
        SET title = ?, is_public = ?, size_bytes = ?, updated_at = ?
        WHERE id = ?
    """, (new_title, new_is_public, new_size, now_str, doc_id))
    conn.commit()

    return {
        "id": doc_id,
        "title": new_title,
        "format": r["format"],
        "filename": r["filename"],
        "size_bytes": new_size,
        "is_public": bool(new_is_public),
        "updated_at": now_str
    }

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, current_user: dict = Depends(get_current_user), conn: sqlite3.Connection = Depends(get_db)):
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, filename FROM documents WHERE id = ?", (doc_id,))
    r = cursor.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Document not found")
    if r["user_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    file_path = Path(STORAGE_DIR) / r["filename"]
    if file_path.exists():
        try:
            os.remove(file_path)
        except Exception:
            pass

    cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()
    return {"message": "Document deleted successfully"}
