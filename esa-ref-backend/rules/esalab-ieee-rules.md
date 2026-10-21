# ESA Lab reference style (IEEE Reference Guide + lab rules)

Source: Prof. Bor-Shing Lin's lab slides (NTPU CSIE, Embedded System and Applications Lab, Oct 2025)
and two approved theses. Where the slides and the IEEE guide differ, the slides win. Where the
Chinese thesis (240401) and the English thesis (240420) differ, the English one is the corrected
version and wins.

## 0. Output conventions used by this tool
- Produce ONE entry per reference, without the leading `[n]` label (the tool re-attaches it).
- Mark italics with `*...*`. Only the journal/conference/book title is italic. Never italicise the
  comma after it, the `vol.`, pages, year, or `et al.`.
- Use typographic quotes `“ ”` around the article/chapter/thesis title. The comma that follows the
  title goes INSIDE the closing quote: `“Title,” *J. Abbrev.*, ...`
- Page ranges use an en dash `–` (U+2013): `pp. 570–578`. Never a hyphen.
- End every entry with a period.
- Never invent data. If a field is unknown, omit it and report it in `issues`. Dates, places and
  numbers in the examples of this document are illustrations only — never copy them into an entry.

## 1. Authors
- Format: initials then surname: `J. Smith`, `P. M. Grant`. One space after each initial.
- Hyphenated given names (common for Taiwanese/Chinese authors): `B.-S. Lin`, `Y.-T. Hsieh`,
  `K.-Y. Ho`. Keep the hyphen, no space after it.
- Suffixes: `W. P. Pratt Jr.`, `J. M. Popovich, Jr.` (keep as in source).
- 1 author: `A`
- 2 authors: `A and B` (no comma)
- 3–6 authors: `A, B, and C` (Oxford comma before `and`)
- 7 or more authors: list the first 6, then `, *et al.*` (italic, period after al):
  `J. Smith, A. Brown, C. Lee, D. Chen, M. Wang, K. Liu, *et al.*, “Title,” ...`
  (The 施宜均 thesis uses `N. Fukushima *et al.*,` with only the first author; the slide rule
  — first six then et al. — is the one to follow.)
- A single-name author (e.g. `Kavita`) is written as is.

## 2. Journal article
`A, B, and C, “Article title,” *J. Abbrev.*, vol. 1, no. 2, pp. 34–56, Mon. Year.`

- Journal name: ALWAYS the abbreviation (lab rule: 「我會全部使用縮寫」). Use the IEEE journal
  abbreviations list for IEEE titles (`IEEE Trans. Biomed. Eng.`, `IEEE Trans. Neural Netw. Learn.
  Syst.`, `IEEE Access`, `IEEE Photon. J.`), ISO4 / LTWA abbreviations otherwise
  (`Bell Syst. Tech. J.`, `J. Appl. Phys.`, `Comput. Methods Programs Biomed.`, `Gait Posture`,
  `Foot Ankle Int.`, `J. Orthop. Res.`, `Sci. Rep.`, `J. Orthop. Sports Phys. Ther.`). Drop
  `&`/`and`/`of`/`the` in abbreviations (`Gait & Posture` -> `Gait Posture`). Single-word
  journals are not abbreviated (`Sensors`, `Ergonomics`, `Diabetes`).
- `vol.` is required when the journal has volumes; `no.` only if an issue number exists.
- Month: abbreviated, 3 letters plus period, except `May`, `June`→`Jun.`, `July`→`Jul.`,
  `Sept.`→`Sep.`: `Jan. Feb. Mar. Apr. May Jun. Jul. Aug. Sep. Oct. Nov. Dec.` Month before year:
  `Jul. 1993`. If the month is unknown, year only: `2011.`
- Article-number journals (no page range, e.g. Sensors, BMJ Open, Sci. Rep., Front. Physiol.):
  `..., *J. Abbrev.*, vol. 109, no. 2, Mon. Year, Art. no. 061301.` — `Art. no.` goes LAST, after
  the date. Do not write `pp.` for these.
- Examples (gold):
  - `S. Chen, B. Mulgrew, and P. M. Grant, “A clustering technique for digital communications channel equalization using radial basis function networks,” *IEEE Trans. Neural Netw.*, vol. 4, pp. 570–578, Jul. 1993.`
  - `R. W. Lucky, “Automatic equalization for digital communication,” *Bell Syst. Tech. J.*, vol. 44, no. 4, pp. 547–588, Apr. 1965.`
  - `C. Lin, L. Liao, Y. Liu, I. Wang, B.-S. Lin, and J. Chang, “Novel Dry Polymer Foam Electrodes for Long-Term EEG Measurement,” *IEEE Trans. Biomed. Eng.*, vol. 58, no. 5, pp. 1200–1207, 2011.`
  - `S. Preu, G. H. Döhler, S. Malzer, L. J. Wang, and A. C. Gossard, “Tunable continuous-wave terahertz photo mixer sources and applications,” *J. Appl. Phys.*, vol. 109, Mar. 2011, Art. no. 061301.`
  - `M. S. Barnish and J. Barnish, “High-heeled shoes and musculoskeletal injuries: a narrative systematic review,” *BMJ Open*, vol. 6, no. 1, Jan. 2016, Art. no. e010053.`
  - `M. Lan, J. Wang, and L. Zhu, “Perception and Range Measurement of Sweeping Machinery Based on Enhanced YOLOv8 and Binocular Vision,” *IEEE Access*, vol. 11, pp. 126398–126408, 2023.`
    (no `in` before a journal name — `in` is only for conferences and books)

## 3. Conference paper
`A, B, and C, “Paper title,” in *Proc. Conf. Abbrev. (ACRONYM)*, City, State (US only), Country, Mon. Day–Day, Year, pp. 34–56.`

- Starts with `in` (not italic) then the italic proceedings name beginning with `Proc.`.
- Abbreviate the conference name; drop `of the`, `on`, `the` (`Proceedings of the 1996 Robotics and
  Automation Conference` -> `Proc. 1996 Robot. Automat. Conf.`). Common words: `Int.`, `Conf.`,
  `Symp.`, `Workshop`, `Annu.`, `Commun.`, `Biomed.`, `Circuits Syst.`, `Electromagn.`, `Theory`.
  If an acronym is well known it may be used alone: `in *Proc. ICCR*`, `in *Proc. IEEE CIBCB*`.
  Both forms are correct: if the original already uses one of them, KEEP it as is — never expand an
  acronym to the full name or shorten a full name to the acronym.
- Location is REQUIRED: `City, Country`; for the USA `City, ST, USA`
  (`Tuskegee, AL, USA`, `Shanghai, China`, `Hiroshima, Japan`, `Dubai, United Arab Emirates`).
- Date: `Mon. Day–Day, Year` when days are known (`Mar. 20–22, 2005`; thesis gold also accepts
  `6–7 Oct. 2022`), otherwise `Mon. Year` (`Oct. 2023`), otherwise `Year`.
- If the year already appears in the conference title (`SSST 2005`), the year may be omitted later.
- Pages LAST: `pp. 124–129.`
- Examples (gold):
  - `B.-S. Lin, Y.-T. Hsieh, and C.-H. Lin, “A wearable ECG monitoring system based on capacitive electrodes,” in *Proc. IEEE Int. Conf. Biomed. Circuits Syst. (BioCAS)*, Shanghai, China, Oct. 2023, pp. 120–123.`
  - `L. S. Carmichael, N. Ghani, P. K. Rajan, K. O’Donoghue, and R. Holt, “Characterization and comparison of modern layer-2 Ethernet survivability protocols,” in *Proc. 37th Southeastern Symp. Syst. Theory (SSST 2005)*, Tuskegee, AL, USA, Mar. 20–22, 2005, pp. 124–129.`
  - `D. Sarkar and K. V. Srivastava, “SRR-loaded antipodal Vivaldi antenna for UWB applications with tunable notch function,” in *Proc. Int. Symp. Electromagn. Theory*, Hiroshima, Japan, 2013, pp. 466–469.`
  - `S. Jain, S. Dash, R. Deorari, and Kavita, “Object Detection Using Coco Dataset,” in *Proc. ICCR*, Dubai, United Arab Emirates, 6–7 Oct. 2022, pp. 1–4.`

## 4. Online journal article (IEEE Xplore etc.)
`A. Surname, “Article title,” *J. Abbrev.*, vol. X, no. Y, pp. xx–yy, Mon. Year. Accessed: Mon. Day, Year. [Online]. Available: URL or https://doi.org/DOI`

- Example: `B.-S. Lin, Y.-T. Hsieh, and C.-H. Lin, “A wearable ECG monitoring system based on capacitive electrodes,” *IEEE Trans. Biomed. Circuits Syst.*, vol. 17, no. 10, pp. 120–123, Oct. 2023. Accessed: Oct. 16, 2025. [Online]. Available: https://doi.org/10.1109/TBCAS.2023.1234567`
- Use this form only when the user asks for an online citation or the item exists only online;
  a normal journal article uses section 2 (no Accessed/Available).

## 5. Web page / news / institutional page / report
- Web page with author: `A. Surname, “Page title,” *Site Name*, Mon. Year. Accessed: Mon. Day, Year. [Online]. Available: URL`
  - `J. Smith, “Deep learning for wearable health monitoring,” *IEEE Spectrum*, May 2024. Accessed: Oct. 16, 2025. [Online]. Available: https://spectrum.ieee.org/wearable-health-monitoring`
- Institutional page without author: `“Title,” *Organisation*, Year. Accessed: Mon. Day, Year. [Online]. Available: URL`
  - `“IEEE Author Center: Reference guide,” *IEEE*, 2024. Accessed: Oct. 16, 2025. [Online]. Available: https://journals.ieeeauthorcenter.ieee.org`
- Report / white paper PDF: `A. Surname, “Document title,” *Publisher*, City, Country, Year. Accessed: Mon. Day, Year. [Online]. Available: URL`
  - `A. Ng, “AI impact report,” *Stanford AI Lab*, Stanford, CA, USA, 2025. Accessed: Oct. 16, 2025. [Online]. Available: https://ai.stanford.edu/report2025.pdf`
- Software / code repository follows the web-page form; the slide form supersedes the older
  `(accessed Apr. 13, 2024)` form found in the 2024 thesis:
  - `G. Jocher, A. Chaurasia, and J. Qiu, “YOLO by Ultralytics,” *GitHub*, Jan. 2023. Accessed: Apr. 13, 2024. [Online]. Available: https://github.com/ultralytics/ultralytics`
- `Accessed:` date format is `Mon. Day, Year` (`Oct. 16, 2025`). The URL has no trailing period.

## 6. arXiv / unpublished
`A, B, and C, “Title,” Year, *arXiv:NNNN.NNNNN*.`
- `S. Urazhdin, N. O. Birge, W. P. Pratt Jr., and J. Bass, “Current-driven magnetic excitations in permalloy-based multilayer nanopillars,” 2003, *arXiv:0303149*.`
- Lab advice: cite arXiv sparingly (not peer reviewed). If a published version exists, cite that instead and say so in `issues`.

## 7. Book and book chapter
- Chapter in edited book:
  `A. Author, “Title of chapter,” in *Title of Book*, X. Editor, Ed., City, ST (US only), Country: Abbrev. Publisher, Year, ch. x, sec. x, pp. xxx–xxx.`
  - `C. Bennett, “What happens when you book an airline ticket? The collection and processing of passenger data post-9/11,” in *Global Surveillance and Policing: Borders, Security, Identity*, E. Zureik and M. Salter, Eds., Cullompton, U.K.: Willan, 2005, pp. 113–138.`
  - `P. C. Dempsey and J. P. Thyfault, “Physiological Responses to Sedentary Behaviour,” in *Sedentary Behaviour Epidemiology*, M. F. Leitzmann, C. Jochem, and D. Schmid, Eds., Cham, Switzerland: Springer, 2018, ch. 5, pp. 109–145.`
- Whole book: `A. Author and B. Author, Eds. *Title of Book*. City, ST, USA: Publisher, Year.`
  - `W. R. Leonard and M. H. Crawford, Eds. *Human Biology of Pastoral Populations*. New York, NY, USA: Cambridge Univ. Press, 2002.`
- Chapter in authored book with edition: `K. S. Saladin, “Support and Movement,” in *Anatomy and Physiology: The Unity of Form and Function*, 9th ed. New York, NY, USA: McGraw Hill, 2021, pp. 349–354.`
- Publisher names abbreviated (`Univ. Press`, `U.K.`).

## 8. Thesis / dissertation
- M.S.: `A. Author, “Title of thesis,” M.S. thesis, Abbrev. Dept., Abbrev. Univ., City, Country, Year.`
  - `N. Kawasaki, “Parametric study of thermal and chemical nonequilibrium nozzle flow,” M.S. thesis, Dept. Electron. Eng., Osaka Univ., Osaka, Japan, 1993.`
- Ph.D.: `A. Author, “Title of dissertation,” Ph.D. dissertation, Abbrev. Dept., Abbrev. Univ., City, ST, USA, Year.`
  - `J. O. Williams, “Narrow-band analyzer,” Ph.D. dissertation, Dept. Elect. Eng., Harvard Univ., Cambridge, MA, USA, 1993.`

## 9. Consistency rules (checked across the whole list)
- One style for the whole list: all journal names abbreviated, never a mix of full and short names.
- Same month style everywhere; same `and`/Oxford-comma style everywhere.
- Numbering `[1]`, `[2]`, ... in order of first citation in the text; the tool keeps the existing numbers.
- Keep the ORIGINAL entry's capitalisation of the article title (both sentence case and Title Case
  appear in approved theses). Use metadata only to fix wrong or missing words, never to re-case a
  title — and do NOT flag capitalisation as an issue.
- Units/maths inside titles follow the IEEE Editorial Style Manual (e.g. `GHz`, not `Ghz`).

## 10. Common mistakes seen in drafts (flag these)
- Full journal name instead of abbreviation (`Scientific Reports` -> `Sci. Rep.`).
- `&` in journal names (`Gait & Posture` -> `Gait Posture`).
- Missing Oxford comma with 3+ authors (`A, B and C` -> `A, B, and C`).
- Hyphen instead of en dash in page ranges (`1-4` -> `1–4`).
- `in` before a journal name.
- Conference cited with the full proceedings title and no `Proc.`, no location, or no date.
- Italic comma after the journal name (EndNote artefact `*Gait Posture, *vol.`).
- Missing `Art. no.` for article-number journals, or `Art. no.` placed before the date.
- `et al.` not italic, or used with fewer than 7 authors.
- Full-width space or tab after `[n]` — the label is followed by a single space.
