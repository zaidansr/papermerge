export const LIMITS={files:100,fileBytes:50*1024*1024,totalBytes:150*1024*1024};
export function validateFiles(files){
 if(!files.length)throw Error('Choose at least one PDF first.');
 if(files.length>LIMITS.files)throw Error('Choose at most 100 PDFs per pack.');
 let total=0;for(const f of files){if(!/\.pdf$/i.test(f.name))throw Error(`${f.name}: choose a PDF file.`);if(f.size>LIMITS.fileBytes)throw Error(`${f.name}: exceeds 50 MB. Choose a smaller PDF.`);total+=f.size;}
 if(total>LIMITS.totalBytes)throw Error('This pack exceeds 150 MB. Remove some files and try again.');
}
export function outputFilename(value){const name=value.trim();if(!name||/[<>:"/\\|?*\x00-\x1f]/.test(name))throw Error('Enter a filename without slashes or special characters.');return /\.pdf$/i.test(name)?name:name+'.pdf';}
export async function mergePdfs(files,PDFDocument,{cancelled=()=>false,progress=()=>{}}={}){
 validateFiles(files);const output=await PDFDocument.create();let pages=0;
 for(let i=0;i<files.length;i++){
  if(cancelled())throw Error('Cancelled. No PDF was saved.');
  const file=files[i];progress(`Reading ${i+1}/${files.length}: ${file.name}`,i,files.length);
  try{const bytes=new Uint8Array(await file.arrayBuffer());if(!new TextDecoder().decode(bytes.slice(0,1024)).includes('%PDF-'))throw Error('Invalid header');const input=await PDFDocument.load(bytes);if(input.isEncrypted||input.getPageCount()===0)throw Error('Encrypted or empty');const copied=await output.copyPages(input,input.getPageIndices());for(const page of copied)output.addPage(page);pages+=copied.length;}
  catch{throw Error(`${file.name}: could not read this PDF. Remove it or use an unlocked, undamaged copy.`);}
  await new Promise(resolve=>setTimeout(resolve,0));
 }
 if(cancelled())throw Error('Cancelled. No PDF was saved.');
 output.setTitle('PaperMerge revision pack');output.setCreator('PaperMerge web');const bytes=await output.save();
 if(cancelled())throw Error('Cancelled. No PDF was saved.');
 const verified=await PDFDocument.load(bytes);if(verified.getPageCount()!==pages)throw Error('Verification failed. No PDF was saved.');
 return {bytes,pages};
}
