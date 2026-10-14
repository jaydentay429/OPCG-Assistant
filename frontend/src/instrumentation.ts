export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { installCardPageStatusPatch } = await import("./lib/cardPageStatus");
    installCardPageStatusPatch();
  }
}
