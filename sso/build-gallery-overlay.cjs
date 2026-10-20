// Compile only the backend overlay; preserve the deployed map/frontend image.
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const input = path.join(__dirname, '../pigallery2-map/overlay/src/backend/middlewares/user');
const output = path.join(__dirname, 'gallery-backend');
fs.mkdirSync(output, {recursive: true});
for (const name of ['OIDCAuthService', 'WildlifeGroupPolicy']) {
  const result = ts.transpileModule(fs.readFileSync(path.join(input, name + '.ts'), 'utf8'), {
    fileName: name + '.ts', reportDiagnostics: true,
    compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS,
      strict: true, sourceMap: false}
  });
  const errors = (result.diagnostics || []).filter(d => d.category === ts.DiagnosticCategory.Error);
  if (errors.length) throw new Error(ts.formatDiagnosticsWithColorAndContext(errors, {
    getCurrentDirectory: () => process.cwd(), getCanonicalFileName: n => n, getNewLine: () => '\n'
  }));
  fs.writeFileSync(path.join(output, name + '.js'), result.outputText);
}
console.log('Compiled gallery backend overlay into sso/gallery-backend; full application type-check is separate.');
