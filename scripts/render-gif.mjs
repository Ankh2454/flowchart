#!/usr/bin/env node
// Record CSS animations at deterministic times; capture only the diagram canvas.
import { chromium } from 'playwright-core';
import { existsSync, mkdtempSync, rmSync, mkdirSync, copyFileSync, globSync } from 'node:fs';
import { execFile, execFileSync } from 'node:child_process';
import { promisify } from 'node:util';
import { tmpdir, homedir } from 'node:os';
import { resolve, join, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';

const help = 'Usage: node render-gif.mjs input.html output.gif [--poster output.png] [--fps 25] [--loop 6000] [--scale 2]';
const args = process.argv.slice(2);
if (args.length === 1 && args[0] === '--help') { console.log(help); process.exit(0); }
let browser;
let framesDir;
try {
  if (args.length < 2) throw new Error(help);
  const input = resolve(args[0]);
  const output = resolve(args[1]);
  if (!existsSync(input)) throw new Error(`Input does not exist: ${input}`);
  const options = { fps: 25, scale: 2 };
  for (let i = 2; i < args.length; i += 2) {
    const key = args[i].replace(/^--/, '');
    if (!args[i].startsWith('--') || !['poster','fps','loop','scale'].includes(key) || args[i + 1] === undefined) throw new Error(`Invalid option: ${args[i]}\n${help}`);
    options[key] = key === 'poster' ? resolve(args[i + 1]) : Number(args[i + 1]);
  }
  for (const key of ['fps','scale','loop']) {
    if (options[key] !== undefined && (!Number.isFinite(options[key]) || options[key] <= 0)) throw new Error(`--${key} must be a positive number`);
  }
  if (new Set([input,output,...(options.poster ? [options.poster] : [])]).size !== (options.poster ? 3 : 2)) throw new Error('Input, GIF and poster paths must be different');
  const ffmpeg = process.env.FFMPEG_PATH || 'ffmpeg';
  try { execFileSync(ffmpeg, ['-version'], {stdio:'ignore'}); }
  catch { throw new Error('ffmpeg not found; install it or set FFMPEG_PATH'); }
  const chrome = [
    process.env.CHROME_PATH,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser',
    process.env.PROGRAMFILES && join(process.env.PROGRAMFILES,'Google/Chrome/Application/chrome.exe'),
    process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA,'Google/Chrome/Application/chrome.exe'),
    ...globSync(join(homedir(),'Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium')),
  ].filter(Boolean).find(existsSync);
  if (!chrome) throw new Error('Chrome/Chromium not found; set CHROME_PATH');
  browser = await chromium.launch({executablePath:chrome});
  const page = await browser.newPage({viewport:{width:1600,height:1200},deviceScaleFactor:options.scale,reducedMotion:'no-preference'});
  const url = pathToFileURL(input); url.searchParams.set('export','1');
  await page.goto(url.href);
  await page.evaluate(() => document.fonts.ready);
  const geometry = await page.evaluate(() => {
    const canvas = document.querySelector('.canvas');
    const svg = canvas?.querySelector('svg');
    const vb = svg?.viewBox.baseVal;
    if (!canvas || !svg || !vb?.width || !vb?.height) throw new Error('Expected .canvas with an SVG and numeric viewBox');
    return {width:Math.ceil(vb.width),height:Math.ceil(vb.height),loop:getComputedStyle(document.documentElement).getPropertyValue('--loop').trim()};
  });
  const loopMatch = geometry.loop.match(/^([\d.]+)(ms|s)$/);
  const cssLoop = loopMatch ? Number(loopMatch[1]) * (loopMatch[2] === 's' ? 1000 : 1) : undefined;
  const loop = options.loop ?? cssLoop ?? 6000;
  if (!Number.isFinite(loop) || loop <= 0) throw new Error('Invalid --loop CSS value');
  if (options.loop !== undefined && cssLoop !== undefined && Math.abs(options.loop-cssLoop)>0.01) throw new Error(`--loop ${options.loop} does not match HTML --loop ${cssLoop}`);
  const count = loop / 1000 * options.fps;
  if (Math.abs(count-Math.round(count)) > 0.000001) throw new Error('loop × fps must produce a whole number of frames');
  await page.setViewportSize({width:geometry.width,height:geometry.height});
  await page.addStyleTag({content:`html,body{margin:0!important;padding:0!important}[data-preview-controls],.controls{display:none!important}.canvas{width:${geometry.width}px!important;height:${geometry.height}px!important;max-width:none!important;margin:0!important}.canvas>svg{width:100%!important;height:100%!important}`});
  const problems = await page.evaluate(loop => {
    const canvas = document.querySelector('.canvas');
    const all = document.getAnimations().filter(a=>canvas.contains(a.effect?.target));
    const problems=[];
    all.forEach((a,i)=>{
      const t=a.effect.getTiming();
      const cycle=Number(t.duration)*(t.direction.startsWith('alternate')?2:1);
      const ratio=loop/cycle;
      if (!Number.isFinite(cycle)||cycle<=0||Math.abs(ratio-Math.round(ratio))>0.00001) problems.push(`animation ${i}: period does not divide loop`);
      if(t.iterations!==Infinity) problems.push(`animation ${i}: use infinite iterations`);
      if(t.delay>0) problems.push(`animation ${i}: positive delay prevents a seamless start`);
      if(a.playbackRate!==1) problems.push(`animation ${i}: playbackRate must be 1`);
      a.pause(); a.currentTime=0;
    });
    return problems;
  },loop);
  if(problems.length) throw new Error(problems.join('\n'));
  await page.evaluate(()=>new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(done))));
  mkdirSync(dirname(output),{recursive:true});
  if(options.poster) mkdirSync(dirname(options.poster),{recursive:true});
  framesDir=mkdtempSync(join(tmpdir(),'flowchart-gif-'));
  const canvas=page.locator('.canvas');
  const frames=Math.round(count);
  for(let i=0;i<frames;i++) {
    await page.evaluate(t=>{
      const canvas=document.querySelector('.canvas');
      document.getAnimations().filter(a=>canvas.contains(a.effect?.target)).forEach(a=>a.currentTime=t);
    },i/options.fps*1000);
    const path=join(framesDir,`f${String(i).padStart(6,'0')}.png`);
    await canvas.screenshot({path});
    if(options.poster && i===Math.floor(frames*0.3)) copyFileSync(path,options.poster);
    if(i%25===0||i===frames-1) console.log(`Frame ${i+1}/${frames}`);
  }
  // Release Chromium before encoding, and keep Node's event loop available during ffmpeg.
  await browser.close();
  browser=undefined;
  await promisify(execFile)(ffmpeg,['-v','error','-y','-framerate',String(options.fps),'-i',join(framesDir,'f%06d.png'),'-vf','split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a','-loop','0',output]);
  console.log(`Saved ${output} (${Math.round(geometry.width*options.scale)} × ${Math.round(geometry.height*options.scale)}, ${frames} frames, ${loop}ms)`);
} catch(error) {
  console.error(error.message); process.exitCode=1;
} finally {
  if(browser) await browser.close();
  if(framesDir) rmSync(framesDir,{recursive:true,force:true});
}
