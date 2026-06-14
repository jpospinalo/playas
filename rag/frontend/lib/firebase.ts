import { getApp, getApps, initializeApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";
import { getFirestore, type Firestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

// Firebase solo se inicializa en el browser. Durante SSR se exponen stubs
// para que los imports no fallen en build; los métodos reales solo se llaman
// desde useEffect (AuthProvider) o event handlers — nunca en SSR.
const _app =
  typeof window !== "undefined"
    ? getApps().length === 0
      ? initializeApp(firebaseConfig)
      : getApp()
    : null;

export const auth: Auth = (_app ? getAuth(_app) : null) as Auth;
export const db: Firestore = (_app ? getFirestore(_app) : null) as Firestore;
