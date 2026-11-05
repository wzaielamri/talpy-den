// An SVG file a webview module imports: esbuild makes it a data: URL (esbuild.mjs, loader)
declare module "*.svg" {
  const url: string;
  export default url;
}
