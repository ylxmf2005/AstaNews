"use client";
// 图片加载失败则隐藏（热链图可能 403/失效，避免显示破图）
export default function Img(props) {
  return <img {...props} onError={(e) => { e.currentTarget.style.display = "none"; }} />;
}
