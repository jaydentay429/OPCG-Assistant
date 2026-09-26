/**
 * Lets `node --test` import the frontend's extensionless TypeScript modules.
 * Only used by the unit-test runner; Next.js resolves these imports itself.
 */
export async function resolve(specifier, context, nextResolve) {
  const isRelative = specifier.startsWith("./") || specifier.startsWith("../");
  if (isRelative && !/\.(?:[cm]?[jt]s|json|node)$/i.test(specifier)) {
    return nextResolve(`${specifier}.ts`, context);
  }
  return nextResolve(specifier, context);
}
