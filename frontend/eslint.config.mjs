// ESLint con le regole di Next.js (core web vitals e TypeScript).
//
// La regola che conta di più è `react-hooks/rules-of-hooks`: un hook dopo un
// `return` anticipato ha già fatto andare in crash la pagina Scheda, e
// TypeScript non se ne accorge. `next build` esegue il controllo e si ferma
// sugli errori, quindi un errore del genere non arriva più in produzione.
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: dirname(fileURLToPath(import.meta.url)) });

const config = [
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts", "probe.mjs"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // Gli apostrofi nel testo JSX ("l'allenamento") sono innocui in React,
      // e in un'interfaccia in italiano sarebbero ovunque da scrivere &apos;.
      "react/no-unescaped-entities": "off",
    },
  },
];

export default config;
