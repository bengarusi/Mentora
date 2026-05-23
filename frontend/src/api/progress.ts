import { apiClient } from "./client";
import type { ProgressMap, StudentProgress } from "../types";

export async function getProgress(): Promise<StudentProgress> {
  const { data } = await apiClient.get<StudentProgress>("/progress/");
  return data;
}

export async function getProgressMap(): Promise<ProgressMap> {
  const { data } = await apiClient.get<ProgressMap>("/progress/map");
  return data;
}
