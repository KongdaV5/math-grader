export type Point = {x:number;y:number};
export type Rect = {left:number;top:number;width:number;height:number};
export type Box = {x:number;y:number;width:number;height:number};

export function screenToImage(point:Point,screen:Rect,image:{width:number;height:number}):Point {
  if(screen.width<=0||screen.height<=0||image.width<=0||image.height<=0)throw new Error("Image dimensions must be positive");
  return {x:Math.max(0,Math.min(image.width,(point.x-screen.left)*image.width/screen.width)),
    y:Math.max(0,Math.min(image.height,(point.y-screen.top)*image.height/screen.height))};
}
export function imageToNormalized(point:Point,image:{width:number;height:number}):Point {
  if(image.width<=0||image.height<=0)throw new Error("Image dimensions must be positive");
  return {x:point.x/image.width,y:point.y/image.height};
}
export function normalizedToImage(box:Box,image:{width:number;height:number}):Box {
  return {x:box.x*image.width,y:box.y*image.height,width:box.width*image.width,height:box.height*image.height};
}
export function normalizedToScreen(box:Box,screen:Rect):Box {
  return {x:screen.left+box.x*screen.width,y:screen.top+box.y*screen.height,
    width:box.width*screen.width,height:box.height*screen.height};
}
export function screenToNormalized(point:Point,screen:Rect,image:{width:number;height:number}):Point {
  return imageToNormalized(screenToImage(point,screen,image),image);
}
