import { z } from "zod";

export const loginSchema = z.object({
  apiKey: z
    .string()
    .min(1, "Master Admin API Key is required.")
    .min(8, "Master key must be at least 8 characters long."),
});

export type LoginFormData = z.infer<typeof loginSchema>;
