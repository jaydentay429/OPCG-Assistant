declare module "opencc-js" {
  export function Converter(options: { from: string; to: string }): (text: string) => string;
}

declare module "opencc-js/dict/*" {
  const dict: string;
  export default dict;
}
