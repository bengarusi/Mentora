import { apiClient } from "./client";
import type { StudentProgress } from "../types";

export async function getProgress(): Promise<StudentProgress> {
  const { data } = await apiClient.get<StudentProgress>("/progress/");
  return data;
}
