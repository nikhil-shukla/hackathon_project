import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, signInWithPopup } from "firebase/auth";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

// Initialize Firebase
let app;
let auth: any;
let googleProvider: any;
let db: any;

try {
  console.info('firebase.ts: initializng Firebase config...', {
    apiKey: firebaseConfig.apiKey ? 'PRESENT' : 'MISSING',
    projectId: firebaseConfig.projectId ? 'PRESENT' : 'MISSING'
  });
  app = initializeApp(firebaseConfig);
  auth = getAuth(app);
  googleProvider = new GoogleAuthProvider();
  db = getFirestore(app);
  console.info('firebase.ts: Firebase connected ✓');
} catch (err) {
  console.error('CRITICAL: Firebase initialization failed:', err);
}

export { auth, googleProvider, db };
export const signInWithGoogle = () => (auth ? signInWithPopup(auth, googleProvider) : Promise.reject('Firebase not initialized'));
