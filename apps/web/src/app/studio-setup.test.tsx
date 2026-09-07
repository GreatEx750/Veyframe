import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";

import Home from "./studio/page";

it("keeps Studio focused on setup with one create action and no editing controls", () => {
  render(<Home />);
  for (const format of ["Product Demo", "Presentation Demo"]) {
    fireEvent.click(screen.getByRole("radio", { name: format }));
    expect(screen.getAllByRole("button", { name: /^Create demo$/i })).toHaveLength(1);
    expect(screen.getByRole("button", { name: /^Create demo$/i })).toHaveAttribute("form", "demo-form");
    expect(within(screen.getByRole("region", { name: "Generation actions" })).getByRole("button", { name: "Create demo" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("Project controls")).queryByRole("button", { name: "Create demo" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Project timeline")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /play (preview|timeline)/i })).not.toBeInTheDocument();
    expect(screen.getByText("Example preview")).toBeInTheDocument();
    expect(screen.getByText(/20-second Northstar example/)).toBeInTheDocument();
  }
});

it("groups the preview and director settings into one workspace, separate from the brief", () => {
  render(<Home />);
  const workspace = screen.getByRole("region", { name: "Preview and settings" });
  expect(within(workspace).getByLabelText("Studio preview")).toBeInTheDocument();
  expect(within(workspace).getByRole("heading", { name: "Director settings" })).toBeInTheDocument();
  expect(within(workspace).getByLabelText("Voice")).toBeInTheDocument();
  expect(within(workspace).getByRole("switch", { name: "Smooth zoom" })).toBeInTheDocument();
  expect(within(workspace).queryByLabelText(/Website URL/)).not.toBeInTheDocument();
});
