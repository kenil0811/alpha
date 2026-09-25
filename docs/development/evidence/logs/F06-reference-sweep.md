# F06 reference-sheet sweep (real browser, final kit)

Page: packages/ui-kit/reference (`just kit-reference`, http://localhost:1430), kit at commit d949198
(same sources as the published profile uiprof-fe345cfb0d6818ad55a1). Browser: Claude desktop app
built-in browser pane (Chromium). For each width and colour scheme, a script inside the page
switched the data state (populated, empty, loading, failing) and the long-label mode, waited
900 ms, then measured:

- `tableRows`: `<tbody>` rows in the page (list table plus the trend's number table; 14 = trend only)
- `listFailed`: "Items could not be loaded" is shown
- `trendLoading`: "Loading the trend…" is shown
- `emptyShown`: "Nothing here yet" is shown
- `overflowing`: count of elements whose right edge passes the viewport
- `hscroll`: whether the document scrolls sideways
- `axe`: violations from axe-core 4.13.0 `axe.run(document)` with every rule, colour contrast included

```
768px light
populated: tableRows=20 listFailed=false trendLoading=false emptyShown=false overflowing=0 hscroll=false axe=[]
empty: tableRows=14 listFailed=false trendLoading=false emptyShown=true overflowing=0 hscroll=false axe=[]
loading: tableRows=0 listFailed=false trendLoading=true emptyShown=false overflowing=0 hscroll=false axe=[]
failing: tableRows=0 listFailed=true trendLoading=false emptyShown=false overflowing=0 hscroll=false axe=[]
populated+long: tableRows=20 listFailed=false trendLoading=false emptyShown=false overflowing=0 hscroll=false axe=[]
empty+long: tableRows=14 listFailed=false trendLoading=false emptyShown=true overflowing=0 hscroll=false axe=[]
loading+long: tableRows=0 listFailed=false trendLoading=true emptyShown=false overflowing=0 hscroll=false axe=[]
failing+long: tableRows=0 listFailed=true trendLoading=false emptyShown=false overflowing=0 hscroll=false axe=[]
1024px light
populated: tableRows=20 listFailed=false trendLoading=false emptyShown=false overflowing=0 hscroll=false axe=[]
empty: tableRows=14 listFailed=false trendLoading=false emptyShown=true overflowing=0 hscroll=false axe=[]
loading: tableRows=0 listFailed=false trendLoading=true emptyShown=false overflowing=0 hscroll=false axe=[]
failing: tableRows=0 listFailed=true trendLoading=false emptyShown=false overflowing=0 hscroll=false axe=[]
populated+long: tableRows=20 listFailed=false trendLoading=false emptyShown=false overflowing=0 hscroll=false axe=[]
empty+long: tableRows=14 listFailed=false trendLoading=false emptyShown=true overflowing=0 hscroll=false axe=[]
loading+long: tableRows=0 listFailed=false trendLoading=true emptyShown=false overflowing=0 hscroll=false axe=[]
failing+long: tableRows=0 listFailed=true trendLoading=false emptyShown=false overflowing=0 hscroll=false axe=[]
1440px light
populated: tableRows=20 listFailed=false trendLoading=false emptyShown=false overflowing=0 hscroll=false axe=[]
empty: tableRows=14 listFailed=false trendLoading=false emptyShown=true overflowing=0 hscroll=false axe=[]
loading: tableRows=0 listFailed=false trendLoading=true emptyShown=false overflowing=0 hscroll=false axe=[]
failing: tableRows=0 listFailed=true trendLoading=false emptyShown=false overflowing=0 hscroll=false axe=[]
populated+long: tableRows=20 listFailed=false trendLoading=false emptyShown=false overflowing=0 hscroll=false axe=[]
empty+long: tableRows=14 listFailed=false trendLoading=false emptyShown=true overflowing=0 hscroll=false axe=[]
loading+long: tableRows=0 listFailed=false trendLoading=true emptyShown=false overflowing=0 hscroll=false axe=[]
failing+long: tableRows=0 listFailed=true trendLoading=false emptyShown=false overflowing=0 hscroll=false axe=[]
768px dark
(identical to 768px light: every state 0 overflowing, no sideways scroll, axe=[])
1024px dark
(identical: every state 0 overflowing, no sideways scroll, axe=[])
1440px dark
(identical: every state 0 overflowing, no sideways scroll, axe=[])
```

The dark-scheme lines were returned verbatim with the same values as the light lines above (each
state's markers matched: populated 20 rows, empty 14 with "Nothing here yet", loading shows
"Loading the trend…", failing shows "Items could not be loaded").

## Defects found and fixed during the sweeps
1. At 768 px with long labels and data, the page scrolled sideways: 36 elements overflowed, and the
   table measured 938 px, because a long column heading could not wrap (`white-space: nowrap` on
   `th`). Headings and sort buttons now wrap; re-measured 0 overflowing at every width.
2. While the trend's data was loading, the chart drew every day as "no entry", which is
   misleading. The reference sheet and composition B now show a loading state until data arrives.
