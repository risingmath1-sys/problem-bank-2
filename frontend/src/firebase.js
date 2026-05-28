import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";
import { getStorage } from "firebase/storage";
import { getAnalytics } from "firebase/analytics";

// 원장님이 제공해주신 실제 Firebase 설정값입니다.
const firebaseConfig = {
    apiKey: "AIzaSyAyn73R7Kj4yFMZPJhCp1FjZMS9Q8NgsNE",
    authDomain: "naegiwangbank.firebaseapp.com",
    projectId: "naegiwangbank",
    storageBucket: "naegiwangbank.firebasestorage.app",
    messagingSenderId: "515632531153",
    appId: "1:515632531153:web:695f36f690f7f798ba67f0",
    measurementId: "G-XH7XS6NGY7"
};

const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);
export const storage = getStorage(app);
export const analytics = getAnalytics(app);
