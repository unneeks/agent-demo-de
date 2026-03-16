import { PRESENT_YEAR } from "../data/traditions.js";

export const TIMELINE_START = -1500;
export const TIMELINE_END = PRESENT_YEAR;

export function getTraditionEndYear(tradition) {
  return tradition.declineTime ?? PRESENT_YEAR;
}

export function sortTraditionsForTimeline(traditions) {
  return [...traditions].sort((left, right) => {
    if (left.originTime !== right.originTime) {
      return left.originTime - right.originTime;
    }
    return left.name.localeCompare(right.name);
  });
}

export function scaleYear(year, width) {
  const range = TIMELINE_END - TIMELINE_START;
  return ((year - TIMELINE_START) / range) * width;
}
