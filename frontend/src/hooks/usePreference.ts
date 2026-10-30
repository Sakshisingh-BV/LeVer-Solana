import { useState } from 'react';
export function usePreference(key: string, initial: boolean): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState(() => { try { const saved = localStorage.getItem(key); return saved === null ? initial : saved === 'true'; } catch { return initial; } });
  return [value, next => { setValue(next); try { localStorage.setItem(key, String(next)); } catch { /* The preference still works for this session. */ } }];
}
