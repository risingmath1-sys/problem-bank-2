import firebase_admin
from firebase_admin import credentials, firestore, storage
from app.core.config import settings
import os

# Global variables to hold client instances
db = None
bucket = None

def initialize_firebase():
    global db, bucket
    
    if firebase_admin._apps:
        # If apps exist, we attempt to get the existing ones
        db = firestore.client()
        bucket = storage.bucket()
        return

    cred_path = settings.FIREBASE_CREDENTIALS_PATH
    bucket_name = settings.FIREBASE_STORAGE_BUCKET
    
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {
            'storageBucket': bucket_name if bucket_name else f"{settings.PROJECT_NAME.lower().replace(' ', '-')}.appspot.com"
        })
        db = firestore.client()
        bucket = storage.bucket()
        print(f"Firebase initialized. Storage Bucket: {bucket.name}")
    else:
        print(f"Warning: Firebase credentials not found at {cred_path}.")

def get_firestore_db():
    if db is None:
        initialize_firebase()
    return db

def get_storage_bucket():
    if bucket is None:
        initialize_firebase()
    return bucket

def upload_file_to_storage(local_path: str, blob_path: str) -> str:
    """
    로컬 파일을 Firebase Storage에 업로드하고 다운로드 URL을 반환합니다.
    """
    try:
        bkt = get_storage_bucket()
        if not bkt:
            return ""
        
        blob = bkt.blob(blob_path)
        blob.upload_from_filename(local_path)
        
        # 외부 접근이 가능하도록 URL 생성 (Make public)
        blob.make_public()
        
        # 브라우저에서 더 잘 인식되는 Firebase Storage URL 형식으로 반환
        return f"https://firebasestorage.googleapis.com/v0/b/{bkt.name}/o/{blob_path.replace('/', '%2F')}?alt=media"
    except Exception as e:
        print(f"  Storage 업로드 실패 ({os.path.basename(local_path)}): {e}")
        return ""
