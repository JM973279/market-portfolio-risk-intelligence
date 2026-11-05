// Real export fidelity and bounded interval interaction, without a browser/API.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
const modules={};
for(const name of ['chart-data','atlas-data']) {
 const code=ts.transpileModule(fs.readFileSync(`src/lib/${name}.ts`,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const moduleValue={exports:{}};
 vm.runInNewContext(code,{module:moduleValue,exports:moduleValue.exports,require:path=>modules[path.replace('./','')]});
 modules[name]=moduleValue.exports;
}
const {atlasDates,nearestDateIndex,clampAtlasWindow,atlasRange,breadthValue,breadthColor,breadthSignals}=modules['atlas-data'];
const dates=['2024-01-02','2024-01-03','2024-01-05'];
assert.equal(nearestDateIndex(dates,'2024-01-04'),1);
assert.equal(nearestDateIndex(dates,'2020-01-01'),0);
assert.equal(nearestDateIndex(dates,'2030-01-01'),2);
assert.equal(nearestDateIndex([],''),0);
assert.equal(JSON.stringify(clampAtlasWindow(dates,100,-2)),'[0,2]');
assert.equal(JSON.stringify(clampAtlasWindow(dates,2,2)),'[1,2]');
assert.equal(JSON.stringify(atlasRange([], '6M')),'[0,0]');
assert.equal(breadthValue(undefined,'x'),null);
assert.equal(breadthValue({x:NaN},'x'),null);
assert.equal(breadthValue({x:0},'x'),0);
assert.equal(breadthValue({x:.9010380623},'x'),.9010380623);
assert.equal(breadthColor(null),'transparent');
assert.equal(breadthColor(.9),'#F3B54A');
assert.notEqual(breadthColor(.899),'#F3B54A');
const global=JSON.parse(fs.readFileSync('public/data/global-markets.json','utf8'));
const monitor=JSON.parse(fs.readFileSync('public/data/korea-monitor.json','utf8'));
const original=JSON.stringify({global,monitor});
const timeline=atlasDates(global,monitor);
assert.equal(timeline.at(-1),global.asOf);
assert.equal(new Set(timeline).size,timeline.length);
for(const range of ['1M','3M','6M','1Y','ALL']){
 const [a,b]=atlasRange(timeline,range);assert.ok(a>=0&&b<timeline.length&&a<b);
}
assert.equal(JSON.stringify(atlasRange(timeline,'ALL')),JSON.stringify([0,timeline.length-1]));
const latest=monitor.latest;
for(const signal of breadthSignals){
 assert.equal(breadthValue(latest,signal.key+'_pct'),latest[signal.key+'_pct']);
}
assert.equal(JSON.stringify({global,monitor}),original);
console.log('PASS: exact source values, nulls, 90% threshold, interval bounds, calendar ranges, untouched exports');
