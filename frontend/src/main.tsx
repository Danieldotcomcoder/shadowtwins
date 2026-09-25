import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/600.css";
import "./styles/global.css";
import "./styles/inspect.css";
import "./styles/pages.css";

import * as Tooltip from "@radix-ui/react-tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { Shell } from "./components/layout/Shell";
import { Loading } from "./components/ui/ui";
import { EvaluatePage } from "./pages/EvaluatePage";
import { AboutPage, NotFoundPage } from "./pages/InfoPages";
import { PracticeListPage } from "./pages/PracticeListPage";
import { LeaderboardPage, ModelPage } from "./pages/ResultsPages";
import { RunPage, RunsPage } from "./pages/RunPages";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

const router = createBrowserRouter([
  {
    element: <Shell />,
    HydrateFallback: () => <Loading />,
    children: [
      { path: "/", element: <EvaluatePage /> },
      { path: "/runs", element: <RunsPage /> },
      { path: "/runs/:runId", element: <RunPage /> },
      { path: "/runs/:runId/items/:jobId", lazy: async () => ({ Component: (await import("./pages/InstancePage")).InstancePage }) },
      { path: "/leaderboard", element: <LeaderboardPage /> },
      { path: "/models/:modelId", element: <ModelPage /> },
      { path: "/practice", element: <PracticeListPage /> },
      { path: "/practice/:instanceId", lazy: async () => ({ Component: (await import("./pages/PracticePages")).PracticePage }) },
      { path: "/about", element: <AboutPage /> },
      { path: "/fixtures", lazy: async () => ({ Component: (await import("./pages/FixturesPage")).FixturesPage }) },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Tooltip.Provider>
        <RouterProvider router={router} />
      </Tooltip.Provider>
    </QueryClientProvider>
  </StrictMode>,
);
