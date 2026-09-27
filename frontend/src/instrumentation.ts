export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { installCardServerErrorRewrite } = await import("./lib/cardErrorStatusPatch");
    installCardServerErrorRewrite();
  }
}
