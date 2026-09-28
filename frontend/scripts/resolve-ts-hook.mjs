/**
 * Lets `node --test` import the frontend's extensionless TypeScript modules
 * and the `@/` alias Next.js resolves. Only used by the unit-test runner.
 */
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const srcRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");

export async function resolve(specifier, context, nextResolve) {
  if (specifier.startsWith("@/")) {
    const base = path.join(srcRoot, specifier.slice(2));
    const file = /\.(?:[cm]?[jt]s|json|node)$/i.test(base) ? base : `${base}.ts`;
    return nextResolve(pathToFileURL(file).href, context);
  }
  const isRelative = specifier.startsWith("./") || specifier.startsWith("../");
  if (isRelative && !/\.(?:[cm]?[jt]s|json|node)$/i.test(specifier)) {
    return nextResolve(`${specifier}.ts`, context);
  }
  return nextResolve(specifier, context);
}
