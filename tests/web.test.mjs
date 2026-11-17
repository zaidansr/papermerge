import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const {PDFDocument,degrees}=createRequire(import.meta.url)('pdf-lib');
import {validateFiles,outputFilename,mergePdfs,LIMITS} from '../docs/merge.mjs';
import {readFile} from 'node:fs/promises';
async function fixture(name,width){const doc=await PDFDocument.create();const page=doc.addPage([width,400]);page.setRotation(degrees(90));return new File([await doc.save()],name,{type:'application/pdf'});}
test('merge keeps file order, dimensions and rotation',async()=>{const a=await fixture('a.pdf',200),b=await fixture('b.pdf',300);const result=await mergePdfs([b,a],PDFDocument);const doc=await PDFDocument.load(result.bytes);assert.equal(result.pages,2);assert.deepEqual(doc.getPages().map(p=>p.getWidth()),[300,200]);assert.equal(doc.getPage(0).getRotation().angle,90);});
test('a broken later file fails the whole operation',async()=>{await assert.rejects(mergePdfs([await fixture('valid.pdf',200),new File(['bad'],'broken.pdf')],PDFDocument),/broken.pdf/);});
test('cancellation never returns an incomplete download',async()=>{await assert.rejects(mergePdfs([await fixture('a.pdf',200)],PDFDocument,{cancelled:()=>true}),/Cancelled/);});
test('file type, count and memory limits have actionable errors',()=>{assert.throws(()=>validateFiles([]),/Choose/);assert.throws(()=>validateFiles([{name:'photo.png',size:1}]),/PDF/);assert.throws(()=>validateFiles(Array(101).fill({name:'a.pdf',size:1})),/100/);assert.throws(()=>validateFiles([{name:'a.pdf',size:LIMITS.fileBytes+1}]),/50 MB/);assert.throws(()=>validateFiles(Array(4).fill({name:'a.pdf',size:LIMITS.fileBytes})),/150 MB/);});
test('filename is normalized and cannot be a path',()=>{assert.equal(outputFilename('revision'),'revision.pdf');assert.equal(outputFilename('REVISION.PDF'),'REVISION.PDF');for(const value of ['','../a','a/b','a\\b'])assert.throws(()=>outputFilename(value));});
test('subject links and both Top 20 collections are valid',async()=>{const data=JSON.parse(await readFile(new URL('../docs/subjects.json',import.meta.url)));for(const [q,subjects]of Object.entries(data.qualifications)){assert.ok(subjects.length>100);const codes=new Set(subjects.map(s=>s.code));assert.equal(data.top20[q].length,20);for(const code of data.top20[q])assert.ok(codes.has(code));for(const s of subjects){assert.match(s.code,/^\d{4}$/);assert.equal(new URL(s.url).hostname,'pastpapers.papacambridge.com');}}});
