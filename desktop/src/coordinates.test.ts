import {test} from "node:test";
import {strict as assert} from "node:assert";
import {screenToImage,imageToNormalized,normalizedToScreen,normalizedToImage} from "./coordinates.ts";

test("screen/image/normalized coordinates survive layout scaling",()=>{
  const natural={width:2000,height:3000};
  const original={left:100,top:60,width:500,height:750};
  const scaled={left:40,top:100,width:1000,height:1500};
  const a=imageToNormalized(screenToImage({x:225,y:247.5},original,natural),natural);
  const b=imageToNormalized(screenToImage({x:290,y:475},scaled,natural),natural);
  assert.deepEqual(a,{x:.25,y:.25});assert.deepEqual(b,a);
  const box={x:.25,y:.25,width:.4,height:.1};
  assert.deepEqual(normalizedToImage(box,natural),{x:500,y:750,width:800,height:300});
  assert.deepEqual(normalizedToScreen(box,scaled),{x:290,y:475,width:400,height:150});
});

test("pointer bounds clamp to image",()=>{
  assert.deepEqual(screenToImage({x:-100,y:1000},{left:10,top:20,width:100,height:100},{width:400,height:400}),{x:0,y:400});
  assert.throws(()=>screenToImage({x:0,y:0},{left:0,top:0,width:0,height:10},{width:1,height:1}));
});
