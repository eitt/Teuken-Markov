"""Build the bounded literature audit from verified metadata and frozen outputs.

Run from the repository root. PDF generation requires reportlab and matplotlib.
This script reads saved results; it never fits a model or downloads source data.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "literature"
CUTOFF = "2026-10-12"
ANALYSIS_COMMIT = "d9815d9f672265236376a30ecc342b661d50b0e6"
REFS = []


def ref(key, authors, year, title, venue, doi, url, access, target, design, overlap, boundary,
        *, volume="", number="", pages="", kind="article", note="", booktitle="", editor=""):
    REFS.append(dict(id=len(REFS)+1, key=key, authors=authors, year=year, title=title,
                     venue=venue, doi=doi, primary_url=url, reading_status=access,
                     outcome_and_scope=target, design=design, overlap=overlap,
                     difference_or_limit=boundary, volume=volume, number=number,
                     pages=pages, kind=kind, note=note, booktitle=booktitle, editor=editor,
                     verified_on=CUTOFF))


ref("murillo2010", "Murillo, María Victoria and Oliveros, Virginia and Vaishnav, Milan", 2010,
    "Electoral Revolution or Democratic Alternation?", "Latin American Research Review",
    "10.1017/S0023879100011122",
    "https://www.cambridge.org/core/journals/latin-american-research-review/article/electoral-revolution-or-democratic-alternation/52EB3EE7115A2A9A2DA209CA83EA1D44",
    "Published full PDF consulted by regional reviewer; publisher abstract and metadata verified",
    "Left/center-left presidential vote share; 18 Latin American countries, 1978-2008",
    "Election regressions with lagged left vote and economic performance conditioned on incumbent ideology",
    "Economic voting and ideological alternation already studied",
    "Vote share includes losing candidates; it is not the annual executive's category",
    volume="45", number="3", pages="87--114", note="Cambridge platform date 2022 is not the original publication year")
ref("baker2011", "Baker, Andy and Greene, Kenneth F.", 2011,
    "The Latin American Left's Mandate: Free-Market Policies and Issue Voting in New Democracies",
    "World Politics", "10.1017/S0043887110000286",
    "https://spaces-cdn.owlstown.com/blobs/iaggewtzqvl42eh7mnn116ekas66",
    "Published full article and author supplement consulted",
    "Vote-revealed leftism; 48 presidential elections in 18 countries, 1996-2008",
    "Aggregate survey/election analysis using GEE and multiple imputation",
    "Distinguishes policy preferences from retrospective punishment",
    "The ideology-weighted vote is different from the ideology of the winning executive",
    volume="63", number="1", pages="43--77")
ref("blanco2013", "Blanco, Luisa and Grier, Robin", 2013,
    "Explaining the Rise of the Left in Latin America", "Latin American Research Review",
    "10.1353/lar.2013.0011",
    "https://www.cambridge.org/core/services/aop-cambridge-core/content/view/80D65F7C778E17F899D7B08AFB801B04/S0023879100010748a.pdf/explaining-the-rise-of-the-left-in-latin-america.pdf",
    "Published full PDF; methods and results consulted",
    "Five-category ideology of elected presidents; 100 elections in 18 countries ending in 2007",
    "Ordered probit/logit with previous-term covariates and commodity exports",
    "Direct predecessor for executive ideology, economic conditions and commodity exposure",
    "Election-level explanatory design; not the annual three-state chronological benchmark",
    volume="48", number="1", pages="68--90",
    note="Abstract reports 1975-2007; methods report 1978-2007. Oil association depends on Venezuela")
ref("brum2025", "Brum, Matías and Cazulo, Paola and Rueda, Horacio and Siniscalchi, Sabrina", 2025,
    "Surfing the Latin American Pink Tide: Secular Trends or Sudden Change in Public Opinion? An Oaxaca-Blinder Approach",
    "Economía LACEA Journal", "10.31389/eco.496",
    "https://economia.lse.ac.uk/articles/10.31389/eco.496/",
    "Publisher full HTML; methods and results consulted",
    "Individual ideological self-placement; Latinobarómetro 1995-2018, selected left-turn and reversal periods",
    "Oaxaca-Blinder and recentered influence function decompositions",
    "Recent direct study of the Pink Tide and its rightward reversal",
    "Decomposition of voter preferences, without strict causal identification or executive transition forecasts",
    volume="24", number="1", pages="228--250", note="Published 5 November 2025")
ref("kayser2009", "Kayser, Mark Andreas", 2009,
    "Partisan Waves: International Business Cycles and Electoral Choice", "American Journal of Political Science",
    "10.1111/j.1540-5907.2009.00410.x",
    "https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-5907.2009.00410.x",
    "Publisher abstract and indexed primary table verified; complete article not directly accessible",
    "Partisan vote intention in eight European countries",
    "Semiannual Eurobarometer analysis of domestic and international economic components",
    "International business cycles can synchronize partisan support",
    "Common economic conditions offer an alternative to geographic ideological contagion",
    volume="53", number="4", pages="950--970")
ref("gleditsch2006", "Gleditsch, Kristian Skrede and Ward, Michael D.", 2006,
    "Diffusion and the International Context of Democratization", "International Organization",
    "10.1017/S0020818306060309",
    "https://www.cambridge.org/core/journals/international-organization/article/diffusion-and-the-international-context-of-democratization/C3806996B1E5100C88DFF3FDACDE631F",
    "Original publisher abstract; model details verified in Zhukov-Stewart's published appendix",
    "Democracy/autocracy transitions across countries",
    "First-order binary Markov/probit transition model; geographic neighbors",
    "Country-state transitions conditioned on international context predate this project",
    "Regime type is not economic left/right ideology; original full text was not directly available",
    volume="60", number="4", pages="911--933")
ref("zhukov2013", "Zhukov, Yuri M. and Stewart, Brandon M.", 2013,
    "Choosing Your Neighbors: Networks of Diffusion in International Relations", "International Studies Quarterly",
    "10.1111/isqu.12008", "https://zhukovyuri.github.io/files/2013_ZS_ISQ.pdf",
    "Published full author PDF; validation and simulation sections consulted",
    "Democratic regime transitions; alternative international networks",
    "Network comparison, 100 random 90/10 validation splits and conditional Arab Spring simulations",
    "Predictive comparison of country networks and political simulations already exists",
    "Random partitions differ from chronological origins; geographic ties need a substantive transmission theory",
    volume="57", number="2", pages="271--287", note="First online 2012; issue year 2013")
ref("segovia2024", "Segovia-Martin, Jose and Rivero, Óscar", 2024,
    "Cross-border political competition", "PLOS ONE", "10.1371/journal.pone.0297731",
    "https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0297731",
    "Publisher full HTML; model and validation sections consulted",
    "Competing ideological populations; empirical U.S./rest-of-world application, 1932-2020",
    "Deterministic/stochastic differential equations; five fixed-window validation splits; simulation averages",
    "Direct predecessor for cross-border ideological dynamics, simulation and validation",
    "Population recruitment model differs from annual executive categories on an Americas country graph",
    volume="19", number="5", pages="e0297731")
ref("antras2025", "Antràs, Pol and Padró-i-Miquel, Gerard", 2025,
    "Exporting Ideology: The Right and Left of Foreign Influence", "Quarterly Journal of Political Science",
    "10.1561/100.00023119", "https://doi.org/10.1561/100.00023119",
    "Published full Harvard-hosted PDF; theory and staggered-election extension consulted",
    "Foreign influence between left/right governments; regional ideological waves",
    "Political-economy theory with capital mobility, redistribution and electoral interaction",
    "A theory of transnational left/right waves already exists",
    "Theoretical mechanisms are not identified by Teuken's geographic covariate; not a tested country-year predictor",
    volume="20", number="1", pages="33--70")
ref("campello2016", "Campello, Daniela and Zucco, Cesar", 2016,
    "Presidential Success and the World Economy", "The Journal of Politics", "10.1086/684749",
    "https://www.journals.uchicago.edu/doi/abs/10.1086/684749",
    "Final publisher abstract/metadata and author bibliographies; final full text not directly verified",
    "Presidential popularity and reelection in a Latin American subset",
    "Analysis of external economic conditions; exact final sample/specification not asserted here",
    "External conditions and electoral accountability have direct regional precedents",
    "Incumbent success need not imply movement left or right",
    volume="78", number="2", pages="589--602", note="First online 29 December 2015; issue year 2016")
ref("arezki2022", "Arezki, Rabah and Djankov, Simeon and Nguyen, Ha and Yotzov, Ivan", 2022,
    "The Political Costs of Oil Price Shocks", "CESifo Working Paper", "",
    "https://www.ifo.de/DocDL/cesifo1_wp9763.pdf",
    "Full primary working-paper PDF; data and exposure specifications consulted",
    "Incumbent-party reelection; 1,042 chief-executive elections, 1985-2020",
    "DPI, oil-price changes interacted with lagged oil-import/GDP exposure; fixed effects and IV robustness",
    "Closest oil-exposure/DPI political-outcome predecessor",
    "Turnover rather than ideology destination; Teuken's merchandise concentration shares use different denominators",
    number="9763", kind="techreport", note="Verified May 2022 working paper; no final journal publication verified")
ref("carreri2017", "Carreri, Maria and Dube, Oeindrila", 2017,
    "Do Natural Resources Influence Who Comes to Power, and How?", "The Journal of Politics", "10.1086/688443",
    "https://static1.squarespace.com/static/5c819dcb51f4d42c9f1c261b/t/5ffd6984a25b58385dd355a1/1610443144515/Carreri_Dube_JOP_2017.pdf",
    "Published full author-linked PDF; specification and results consulted",
    "Colombian local elections and pro-paramilitary politicians, 1997-2007",
    "Oil-price levels interacted with pre-period municipal production; fixed effects and regional trends",
    "Oil exposure and the political identity of winners already linked empirically",
    "Conflict-specific mechanism and local outcomes do not establish a universal national rightward effect",
    volume="79", number="2", pages="502--518")
ref("gallego2018", "Gallego, Jorge", 2018,
    "Natural disasters and clientelism: The case of floods and landslides in Colombia", "Electoral Studies",
    "10.1016/j.electstud.2018.08.001",
    "https://pure.urosario.edu.co/en/publications/natural-disasters-and-clientelism-the-case-of-floods-and-landslid/",
    "Primary institutional abstract/metadata; publisher introduction and section previews consulted by shock reviewer",
    "Incumbent-party reelection in Colombian local elections around 2010-2011 rains",
    "Difference-in-differences; relief/clientelism mechanism",
    "ENSO-linked disasters and political survival already studied",
    "Disasters can favor incumbents; neither direction nor survival follows automatically from an adverse shock",
    volume="55", pages="73--88")
ref("visconti2022", "Visconti, Giancarlo", 2022,
    "After the Flood: Disasters, Ideological Voting and Electoral Choices in Chile", "Political Behavior",
    "10.1007/s11109-022-09814-1", "https://www.giancarlovisconti.com/pdfs/Visconti.2022.POBE.pdf",
    "Published full author PDF; design and findings consulted",
    "Candidate preferences after Chile's 2015 floods",
    "Disaster-exposure natural experiment combined with a candidate conjoint and interviews",
    "Direct predecessor for disaster exposure and ideological choice",
    "Left/independent candidate preference is not an observed national executive-category switch",
    volume="44", pages="1985--2004")
ref("smirnov2018", "Smirnov, Oleg and Steinwand, Martin C. and Xiao, Tingyin and Zhang, Minghua", 2018,
    "Climate Impacts, Political Institutions, and Leader Survival: Effects of Droughts and Flooding Precipitation",
    "Economics of Disasters and Climate Change", "10.1007/s41885-018-0024-7",
    "https://link.springer.com/article/10.1007/s41885-018-0024-7",
    "Publisher abstract/metadata only; detailed estimator not verified",
    "Regular/irregular world-leader exits, 1950-2010",
    "Georeferenced climate and Archigos data; institutional moderation",
    "Cross-national climate and leader-survival research already exists",
    "Leader exit includes term limits and need not change party ideology; not evidence for an ONI direction coefficient",
    volume="2", pages="181--201")
ref("margalit2026", "Margalit, Yotam and Solodoch, Omer", 2026,
    "Electoral responses to economic crises", "American Journal of Political Science", "10.1111/ajps.70008",
    "https://onlinelibrary.wiley.com/doi/10.1111/ajps.70008",
    "Publisher full HTML; methods and main results consulted",
    "Party vote and ideological composition in 24 developed democracies, 1945-2019",
    "Cross-national party/election panel and individual evidence; separates right gains from incumbent punishment",
    "Recent direct predecessor on crisis-related ideological direction",
    "Its scope and identification arguments differ from annual Americas predictions; rightward gains are not a universal rule",
    volume="70", number="3", pages="1247--1261", note="First online 27 August 2025; journal issue 2026")
ref("birch2026", "Birch, Sarah", 2026,
    "Floods and democratic attitudes: evidence from Latin America", "Climatic Change", "10.1007/s10584-026-04259-5",
    "https://link.springer.com/article/10.1007/s10584-026-04259-5",
    "Publisher full HTML; design and findings consulted",
    "Democratic attitudes around seven floods in six Latin American/Caribbean countries, 2016-2019",
    "Unexpected events during survey design",
    "Recent regional hazard/political-attitude evidence",
    "Democratic attitudes are not left/right executive orientation or electoral results",
    volume="179", pages="168", note="Published 4 August 2026; single author")
ref("herre2023", "Herre, Bastian", 2023,
    "Identifying Ideologues: A Global Dataset on Political Leaders, 1945-2020", "British Journal of Political Science",
    "10.1017/S0007123422000217",
    "https://www.bastianherre.com/_files/ugd/654001_d5f5c5db94dc4f5c8f5e9dfce92ff321.pdf",
    "Author accepted full manuscript and final publisher metadata; source comparison consulted",
    "Annual economic ideology of chief executives in 182 countries, 1945/independence-2020",
    "GLI coding, source comparison and descriptive applications",
    "Public executive-ideology data and DPI comparisons already available",
    "Teuken reuses data; its adjacent-date regional audit is incremental, and GLI draws on DPI among other sources",
    volume="53", number="2", pages="740--748", note="First online 6 July 2022; final issue year 2023")
ref("delacerda2026", "de la Cerda, Nicolás and Bakker, Ryan and Jolly, Seth and Polk, Jonathan and Dassonneville, Ruth and Koedam, Jelle and Leslie, Patrick and Sheppard, Jill and Zur, Roi", 2026,
    "A Global Scale of Economic Left-Right Party Positions: Cross-National and Cross-Expert Perceptions of Party Placements",
    "The Journal of Politics", "10.1086/736578", "https://www.journals.uchicago.edu/doi/full/10.1086/736578",
    "Publisher full HTML; measurement framework consulted",
    "Expert economic left-right party placements across several world regions including Latin America",
    "Anchoring vignettes and Bayesian scaling to examine comparability and bias",
    "Cross-national ideological measurement requires assessment",
    "Party positions differ from executive labels; does not establish an annual transition forecast",
    volume="88", number="4", note="Online 9 July 2026; page range not verified and intentionally omitted")
ref("ward2010", "Ward, Michael D. and Greenhill, Brian D. and Bakke, Kristin M.", 2010,
    "The perils of policy by p-value: Predicting civil conflicts", "Journal of Peace Research", "10.1177/0022343309356491",
    "https://journals.sagepub.com/doi/10.1177/0022343309356491",
    "Publisher abstract, notes and metadata; full main text not directly verified",
    "Predictive assessment of civil-war models",
    "Comparison of statistical significance and out-of-sample predictive performance",
    "Political-science predictive benchmarking predates this study",
    "Useful validation precedent, not the same ideological outcome",
    volume="47", number="4", pages="363--375")
ref("gneiting2007", "Gneiting, Tilmann and Raftery, Adrian E.", 2007,
    "Strictly Proper Scoring Rules, Prediction, and Estimation", "Journal of the American Statistical Association",
    "10.1198/016214506000001437", "https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf",
    "Published full author PDF; categorical scoring framework consulted",
    "General probabilistic forecasts, including categorical outcomes",
    "Theory of proper scoring rules",
    "Brier/log-score evaluation is established statistical practice",
    "Proper scores strengthen evaluation; using them is not an invented method",
    volume="102", number="477", pages="359--378")
ref("bunker2020", "Bunker, Kenneth", 2020,
    "A two-stage model to forecast elections in new democracies", "International Journal of Forecasting",
    "10.1016/j.ijforecast.2020.02.004",
    "https://kennethbunker.github.io/publications/2020-two-stage-model-forecast-elections-new-democracies/",
    "Author abstract and metadata only; final detailed algorithm not verified",
    "Candidate electoral results in 11 Latin American countries",
    "Filtered/weighted polls followed by Bayesian estimation",
    "Regional electoral forecasting is not a new application area",
    "The abstract's Markov-chain wording does not establish a substantive country-ideology transition model",
    volume="36", number="4", pages="1407--1419")
ref("murillo2011", "Murillo, María Victoria and Oliveros, Virginia and Vaishnav, Milan", 2011,
    "Economic Constraints and Presidential Agency", "Johns Hopkins University Press", "10.1353/book.1866",
    "https://mariavictoriamurillo.com/wp-content/uploads/2020/06/voting-for-the-left-or-governing-on-the-leftmurillo_oliveros_vaishnav2011.pdf",
    "Published chapter scan verified by regional reviewer; full author manuscript consulted",
    "Economic ideology while governing; 106 presidential terms in 18 countries, 1978-2008",
    "Five-category ordered probit with external economic constraints and political controls",
    "Very direct predecessor for government ideology and economic constraints",
    "Implemented-policy/term-level coding differs from annual executive-party snapshots",
    pages="52--70", kind="incollection", booktitle="The Resurgence of the Latin American Left",
    editor="Levitsky, Steven and Roberts, Kenneth M.",
    note="DOI belongs to the edited book, not an independently verified chapter DOI; author manuscript has a different title")
ref("moraes2020", "Moraes, Juan A. and Luján, Diego", 2020,
    "The Electoral Success of the Left in Latin America: Is There Any Room for Spatial Models of Voting?",
    "Latin American Research Review", "10.25222/larr.466",
    "https://www.cambridge.org/core/journals/latin-american-research-review/article/electoral-success-of-the-left-in-latin-america-is-there-any-room-for-spatial-models-of-voting/F1ACAC939C6595005137F58384A5D452",
    "Publisher full HTML; methods and results consulted",
    "Candidate evaluation; supplementary vote-intention analyses; CSES elections in five Latin American countries",
    "Directional and proximity utilities in ideological space; comparative and Brazil analyses",
    "Spatial voting theory has already been applied to the Latin American left",
    "Spatial here means policy-position space, not a geographic network of countries",
    volume="55", number="4", pages="691--705", note="Original issue 2020; Cambridge platform posting 2022")
ref("correa2015", "Corrêa, Diego Sanches", 2015,
    "Economia, Ideologia e Eleições na América Latina", "Dados", "10.1590/00115258201548",
    "https://www.scielo.br/j/dados/a/KTK8DvYN6y6kfvJHzY6DG8p/?lang=pt",
    "Primary full HTML/PDF consulted by regional reviewer",
    "Change in incumbent-supported candidate vote share; 76 analyzed elections in 18 democracies",
    "Economic voting regressions conditioned on left/center/right ideology and institutional responsibility",
    "Three ideological classes and macroeconomic interactions already used regionally",
    "Ideology conditions the vote outcome rather than being the next-state target",
    volume="58", number="2", pages="401--425")
ref("flechtner2024", "Flechtner, Svenja and Middelanis, Martin", 2024,
    "The role of the commodity price boom in shaping public social spending: Evidence from Latin America",
    "World Development", "10.1016/j.worlddev.2024.106717",
    "https://refubium.fu-berlin.de/bitstream/handle/fub188/44798/1-s2.0-S0305750X24001876-main.pdf?isAllowed=y&sequence=1",
    "Published full institutional PDF consulted by regional reviewer; reopens were rate-limited",
    "Social spending in 16 Latin American countries, 1990-2019",
    "Country-specific SVARs and local-projection robustness; commodity terms of trade and ideological heterogeneity",
    "Recent commodity-exposure/government-ideology comparisons already exist",
    "Fiscal responses are not ideology transitions; commodity terms of trade differ from fuel concentration shares",
    volume="182", pages="106717")


INTRO = """# Teuken-Markov: literature review and novelty assessment

Review cutoff: 12 October 2026. Assessed analysis: commit d9815d9f672265236376a30ecc342b661d50b0e6.

## Assessment

The present analysis has low methodological novelty and a plausible, incremental empirical contribution. Regional ideological waves, executive-ideology models, spatial political transitions, cross-border simulations and shock-exposure interactions all have close precedents. The defensible contribution is a reproducible assessment of how measurement choices and predictive evaluation affect the study of annual executive-orientation transitions in the Americas. Its bibliographic priority has not been established.

The current results favor positioning the paper as a benchmark and measurement audit. They do not establish that adding geography, oil or ENSO reliably anticipates ideological switches. A lack of aggregate improvement is useful evidence within the evaluated design, but it does not show that those mechanisms are absent from politics.

This is a targeted scoping review of primary research, not an exhaustive systematic review. It includes foundational work and publications available by the cutoff, including 2024-2026 studies. The inventory distinguishes full-text consultation from abstract/preview access and marks version differences. Finding no identical combination in this search does not establish a worldwide first.

## What the analysis actually studies

The outcome is the next annual Left, Center or Right executive category recorded by the source. DPI primarily supplies economic orientation associated with the executive party; GLI codes officeholder economic ideology and is analyzed separately. A change of person, a party defeat, voter self-placement, an ideological vote share and a policy change are distinct outcomes. Several Americas countries have parliamentary systems, so the full sample should be described as executive orientation rather than exclusively presidential ideology.

The implemented methods are smoothed empirical Markov probabilities, regularized multinomial models, duration and geographic composition features, lagged observed drivers, and conditional Monte Carlo paths. Countries can be treated as statistical agents on a graph, but the prototype does not implement a new voter-level behavioral mechanism or an election-scheduled mechanistic agent model.

The intended geographic universe contains 35 sovereign Americas countries; available classifications cover fewer countries and years. DPI observations span 1975-2023; GLI source observations span 1945-2020, relabeled to adjacent January dates in 1946-2021. These dates do not create additional observations. Unknown classifications remain missing, rather than becoming Center.
"""

THEMES = """## How the literature changes the novelty claim

### Regional ideology and political alternation

The distinction between electoral demand and governing orientation is established. Murillo, Oliveros and Vaishnav (2010) analyze retrospective left voting [1], whereas Baker and Greene (2011) study an economic-policy mandate using ideology-weighted votes [2]. Their different findings and outcomes should be treated as an empirical debate, rather than reduced to a single explanation of the region. Blanco and Grier (2013) directly model five-category executive ideology with economic and commodity variables [3]. Murillo, Oliveros and Vaishnav (2011) examine economic constraints and ideology while governing [23]. These studies rule out claiming the first quantitative model of Latin American government ideology.

Brum et al. (2025) explicitly study both the Pink Tide and its reversal through decompositions of voter self-placement [4]. Corrêa (2015) already combines three incumbent ideological classes with economic voting variables [25]. Moraes and Luján (2020) compare directional and proximity voting models [24]; their spatial dimension is ideological position, not geographic contact between countries. Executive maps therefore cannot establish that the continent's citizens are predominantly left-wing, or that every country belongs to one uniform historical wave.

### International co-movement, networks and simulation

Kayser (2009) links international co-movement in partisan support to shared business cycles [5]. Consequently, neighboring ideological similarity can reflect common conditions, rather than transmission. Gleditsch and Ward (2006) provide a transition-model precedent for democracy [6]; the Markov specification was verified through the published appendix of Zhukov and Stewart (2013), whose study also compares alternative networks, evaluates held-out predictions and simulates political change [7]. Its random partitions differ from Teuken's chronological origins, but predictive network evaluation itself is not new.

Segovia-Martin and Rivero (2024) are a particularly close simulation predecessor: they model cross-border ideological competition, assess validation windows and project conditional paths [8]. Antràs and Padró-i-Miquel (2025) supply a direct political-economy theory of foreign influence between left/right governments and regional waves [9]. Teuken uses a different unit and outcome; it has not identified those papers' mechanisms. A geographic proximity edge does not measure communication, capital influence or party coordination.

### Economic and climatic shocks

Campello and Zucco (2016) connect external conditions to presidential success [10]. Arezki et al. (2022), a verified working paper, use DPI elections and oil-price exposure to study incumbent-party survival [11]. Carreri and Dube (2017) relate oil exposure to the identity of local winners in Colombia through an armed-conflict mechanism [12]. Thus, neither external shocks nor oil-price-by-exposure interactions provide methodological novelty here. Flechtner and Middelanis (2024) add recent regional evidence on commodity terms of trade and social spending [26], which remains a different outcome.

Margalit and Solodoch (2026; online 2025) explicitly distinguish crisis-related right gains from incumbent punishment [16]. Weather-related effects also vary by outcome and context. Gallego (2018) studies incumbent benefits after Colombian disasters [13]; Visconti (2022) studies left/independent candidate preferences after Chilean floods [14]; Smirnov et al. (2018) examine leader exits worldwide [15]. Birch (2026) studies democratic attitudes after Latin American floods [17]. None permits imposing one universal leftward or rightward transition sign on Teuken.

### Measurement and prediction

Herre (2023) already provides global executive-ideology data and comparisons with DPI [18]. Teuken's regional date/role alignment and disagreement reporting can improve transparency, but they do not create a new global ideology dataset or the first source comparison. GLI uses DPI among its source materials, so agreement is not independent validation. The cross-national party-position scaling in de la Cerda et al. (2026) further motivates measurement checks [19].

Predictive benchmarking in political science predates this application [20], as do proper probabilistic scores [21]. Bunker (2020) also supplies a Latin American electoral-forecasting precedent [22]. Its abstract's reference to Markov chains is insufficient to classify the algorithm as a substantive country-ideology transition model. Teuken's potential contribution comes from the empirical comparison and its findings, rather than from renaming standard methods.
"""

NOVELTY_ROWS = [
    ["Dimension", "Present assessment", "Defensible wording"],
    ["Theory", "Limited", "Tests predictive implications consistent with established regional-wave, accountability and diffusion literatures"],
    ["Methods", "Low", "Applies standard Markov, multinomial and Monte Carlo tools; no new estimator or identified mechanism"],
    ["Data", "Incremental", "Reproducible integration of existing public sources with explicit dates, missingness and role choices"],
    ["Application", "Potentially useful", "Annual three-state transitions across the Americas, with separate historical and driver panels"],
    ["Empirical result", "Benchmark contribution", "Reports limited gains and weak switch anticipation relative to simple baselines"],
    ["Causal interpretation", "Not established", "Conditional associations and fitted-input sensitivity; no identified contagion or shock intervention effect"],
]

PRIORITIES = """## Three priorities for a stronger paper

1. **Separate transition opportunity from destination.** Evaluate a two-part or competing-risk design: first the probability that orientation changes, then the destination conditional on a change. Add verified election dates, term rules and competitive-election sensitivity. A party can change without changing orientation, and a category can be recoded without an electoral defeat. These are standard modeling options, not newly invented methods.

2. **Test whether a network adds information beyond shared conditions.** Compare geographic and substantively motivated trade/institutional networks, global or regional ideological composition, and network permutation baselines. Retain duration and common-shock controls. Quantify paired score differences with uncertainty that respects dependence across countries and time. Better predictive performance would still not identify contagion without additional design assumptions.

3. **Make the empirical claim robust to measurement and evaluation choices.** Compare model performance on matched cases within each source; audit disputed labels; report class-specific transitions, change-risk calibration, precision-recall and threshold-dependent decisions. Preserve a future holdout and document publication vintages before claiming real-time forecasting. Negative results should be replicated across reasonable specifications before making a broad claim that added drivers are uninformative.

Further extensions should follow the question rather than add event dummies indiscriminately. The lagged Ukraine-war question requires outcomes later than the January 2023 endpoint. Country-level drought, precipitation and temperature anomalies would be more directly interpretable as local hazards than annual ONI alone. ENSO variability is not a measure of anthropogenic climate change. Election-scheduled or asynchronous updates and checks of simulated durations, transition rates and synchronization would strengthen a country-agent simulation.

## Interpretation limits required in the manuscript

- Geographic dependence is observational; proximity is not a verified influence channel.
- Revised historical macro/climate inputs support retrospective chronological validation, not reconstruction of information available at each historical forecast date. Even some previous-year observations were published after January 1.
- Fuel imports as a share of merchandise imports and fuel exports as a share of merchandise exports have different denominators. Their difference is not net fuel exposure.
- ONI is a broad ENSO proxy. Annual signed averages can hide seasonal and phase differences; teleconnections vary across countries.
- Oil input contrasts hold other fitted features fixed. They describe conditional sensitivity rather than a coherent intervention or general-equilibrium response.
- Monte Carlo bands describe path variability conditional on the fitted model and scenario. They do not include parameter, coding, structural-model or future-shock uncertainty.
- A source label is not a direct measure of all policies, democratic quality or population ideology. Neither public data nor a longer time span removes classification uncertainty.
"""

DRAFT = """## Manuscript-ready related work

Latin America's leftward and rightward movements have been studied as electoral responses, changes in policy preferences and changes in governing orientation. These outcomes do not coincide. Murillo, Oliveros and Vaishnav (2010) emphasize retrospective voting [1], whereas Baker and Greene (2011) analyze the policy content of an ideology-weighted electoral mandate [2]. More directly related to our outcome, Blanco and Grier (2013) model elected executive ideology [3], and Murillo, Oliveros and Vaishnav (2011) examine economic constraints on ideology while governing [23]. Brum et al. (2025) extend the debate to the Pink Tide's reversal using voter-preference decompositions [4]. This literature establishes that a change in the governing category cannot be read directly as a change in the electorate's ideological distribution.

International similarity also admits several explanations. Partisan support can co-move because countries share economic fluctuations (Kayser 2009) [5]. Spatial transition models and predictive network comparisons have established precedents in democratization research (Gleditsch and Ward 2006; Zhukov and Stewart 2013) [6,7]. Cross-border ideological simulation is already developed by Segovia-Martin and Rivero (2024) [8], while Antràs and Padró-i-Miquel (2025) theorize left/right foreign influence and regional waves [9]. These contributions motivate international predictors but do not imply that geographic adjacency alone identifies an influence mechanism.

External shocks require a further distinction between incumbent survival and ideological direction. Campello and Zucco (2016) examine presidential success under external economic conditions [10]; Arezki et al. (2022) study oil exposure and incumbent-party reelection [11]; and Margalit and Solodoch (2026) separate crisis-related right gains from punishment of incumbents [16]. Disaster studies likewise consider different outcomes, including local incumbent survival (Gallego 2018) [13], candidate preferences (Visconti 2022) [14], leader exits (Smirnov et al. 2018) [15] and democratic attitudes (Birch 2026) [17]. Their findings motivate context-sensitive hypotheses rather than a universal direction of change following adversity.

Our analysis addresses the predictive reliability of an annual executive-orientation representation. Public classifications make historical comparison possible, but their definitions and missingness matter. Herre (2023) already compares GLI with other sources [18], and de la Cerda et al. (2026) examine comparability in party-position measurement [19]. We therefore treat DPI and GLI as separate measurement exercises and do not regard their agreement as independent validation. Established predictive assessment and scoring principles [20,21] guide the comparison of persistence, Markov and covariate-based probabilities. The empirical question is whether additional information improves predictions under this particular outcome, sample and temporal evaluation design.

## Manuscript-ready contribution and result

This study provides a reproducible benchmark of annual executive political-orientation transitions in the Americas. It combines explicit source and observation-date audits with chronological out-of-sample comparisons against persistence and Markov baselines. Geographic composition and lagged oil and ENSO exposure enter as candidate predictors across separate specifications, while conditional simulations illustrate the implications of fitted probabilities. The contribution concerns the reliability and limits of this empirical design; it does not introduce a new transition estimator or identify cross-border ideological contagion.

The expanded DPI evaluation contains 1,007 country-year cases and 93 observed orientation changes. Markov achieves a multiclass Brier score of 0.1712, compared with 0.1745 for the combined oil-ENSO model. The latter ranks change risk somewhat better, but does not improve the aggregate proper score. Four reduced multinomial specifications correctly select the new orientation in only two of the 93 changing cases, and none correctly selects it in the 60 changing cases with origins from 2000 onward. The separate GLI assessment similarly exposes limited anticipation of changes. These observations support a careful benchmark of predictive limits, rather than a claim of reliable ideological-switch forecasting. They do not establish that economic or international mechanisms are causally unimportant.

Suggested title: **Persistence, Measurement and Predictive Limits of Executive Ideological Transitions in the Americas**.

A stronger substantive claim should follow new evidence from the prioritized analyses, rather than a stronger novelty adjective. Publication fit and compliance with Teuken's current author requirements need a separate check against a supplied or verified journal guide.
"""

SEARCH = """## Review scope and search record

Searches were conducted on 12 October 2026 using two web-search engines and citation-following. Search families included: Latin America + left turn/Pink Tide/reversal + executive ideology/economic voting; ideology + Markov + Latin America + governments/prediction; spatial democratization + transition model/network validation; cross-border political competition + ideology/simulation; oil/commodity shocks + exposure/elections/ideology; ENSO/El Niño + elections/incumbency; climate/disaster shocks + ideological voting/leader survival; global executive ideology + DPI/GLI measurement. Targeted author/title/DOI queries resolved bibliographic details and accessible primary versions.

Selection prioritized research that overlaps in outcome, unit, explanatory drivers, transition dynamics or validation design. Peripheral results and unverified conference leads were not used to establish novelty. The 26-entry inventory is a curated set of relevant studies, not a count of all screened records. No Scopus/Web of Science database export, preregistered search protocol or exhaustive exclusion log was produced. Abstract-only items support only the limited claims stated in their inventory rows. Full-text consultation does not mean that every appendix was independently replicated.

Publication metadata use the journal issue year where verified; platform migration dates and preprint versions are identified separately. Arezki et al. is explicitly a working paper. The DOI attached to Murillo et al.'s chapter refers to the edited book. Unverified page ranges were omitted. The review is current to its stated cutoff, rather than a guarantee against all existing or subsequent prior art.

No new model was fitted, no historical government was recoded and no inferential significance test was conducted for this review. The results were read from the assessed repository's saved outputs. Their reported ordering is descriptive: sampling uncertainty for paired performance differences has not yet been established.
"""


def md_table(rows):
    return "\n".join(["| " + " | ".join(rows[0]) + " |",
                      "| " + " | ".join(["---"] * len(rows[0])) + " |"] +
                     ["| " + " | ".join(map(str, row)) + " |" for row in rows[1:]])


def cite_line(r):
    doi = ("https://doi.org/" + r["doi"]) if r["doi"] else r["primary_url"]
    vol = r["volume"] + (f'({r["number"]})' if r["volume"] and r["number"] else "")
    loc = ", ".join(x for x in [vol, r["pages"].replace("--", "-")] if x)
    if r["kind"] == "techreport":
        loc = "No. " + r["number"]
    if r["kind"] == "incollection":
        venue = f'In {r["booktitle"]}, pp. {r["pages"].replace("--", "-")}. {r["venue"]}'
    else:
        venue = r["venue"] + (", " + loc if loc else "")
    end = "" if r["title"].endswith(("?", "!", ".")) else "."
    return f'[{r["id"]}] {r["authors"].replace(" and ", "; ")} ({r["year"]}). {r["title"]}{end} {venue}. {doi}'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sources.json").write_text(json.dumps(dict(review_cutoff=CUTOFF,
        analysis_commit=ANALYSIS_COMMIT, review_type="Targeted scoping review", studies=REFS),
        ensure_ascii=False, indent=2) + "\n")
    with (OUT / "literature_matrix.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(REFS[0]))
        w.writeheader()
        w.writerows(REFS)
    bib = []
    for r in REFS:
        fields = dict(author=r["authors"], title="{" + r["title"] + "}", year=r["year"])
        if r["kind"] == "article":
            fields.update(journal=r["venue"])
        elif r["kind"] == "techreport":
            fields.update(institution="CESifo", type="Working Paper")
        else:
            fields.update(booktitle=r["booktitle"], editor=r["editor"], publisher=r["venue"])
        for k in ["volume", "number", "pages", "doi", "note"]:
            if r[k]:
                fields[k] = r[k]
        fields["url"] = r["primary_url"]
        fields["urldate"] = CUTOFF
        bib.append("@" + r["kind"] + "{" + r["key"] + ",\n" +
                   ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items()) + "\n}")
    (OUT / "references.bib").write_text("\n\n".join(bib) + "\n")
    nearest = [["Study", "Prior overlap", "Difference from this analysis"]]
    for key in ["blanco2013", "murillo2011", "kayser2009", "zhukov2013", "segovia2024", "antras2025",
                "arezki2022", "margalit2026", "visconti2022", "herre2023"]:
        r = next(x for x in REFS if x["key"] == key)
        names = {"blanco2013":"Blanco & Grier", "murillo2011":"Murillo et al.", "kayser2009":"Kayser",
                 "zhukov2013":"Zhukov & Stewart", "segovia2024":"Segovia-Martin & Rivero",
                 "antras2025":"Antràs & Padró-i-Miquel", "arezki2022":"Arezki et al.",
                 "margalit2026":"Margalit & Solodoch", "visconti2022":"Visconti", "herre2023":"Herre"}
        nearest.append([f'[{r["id"]}] {names[key]} ({r["year"]})',
                        r["overlap"], r["difference_or_limit"]])
    with (OUT / "closest_studies.csv").open("w", newline="") as f:
        csv.writer(f).writerows(nearest)
    rows = [["Panel / model", "Cases", "Observed changes", "Multiclass Brier", "Correct new category / changes"]]
    evidence = []
    for panel, directory in [("DPI drivers", "dpi_drivers"), ("GLI HOG", "gli_hog")]:
        with (ROOT / f"outputs/extensions/{directory}/metrics.csv").open() as f:
            metrics = list(csv.DictReader(f))
        changed = {r["model"]: r for r in metrics if r["subset"] == "changed"}
        for m in [r for r in metrics if r["subset"] == "all"]:
            if m["model"] not in ["persistence", "markov", "lean_oil_enso", "history_network"]:
                continue
            hits = round(float(changed[m["model"]]["accuracy"]) * int(m["changes"]))
            labels = {"persistence":"Persistence", "markov":"Markov", "lean_oil_enso":"Reduced + oil + ENSO",
                      "history_network":"Duration + network"}
            rows.append([panel + " / " + labels[m["model"]], m["n"], m["changes"],
                         f'{float(m["brier_multiclass"]):.4f}', f'{hits}/{m["changes"]}'])
            evidence.append(dict(panel=panel, **m, correct_new_category=hits))
    (OUT / "result_evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    results = """## What the saved results permit

The following are frozen output values, not newly estimated results. DPI's expanded driver evaluation uses origins 1985-2022; the GLI head-of-government panel is separate. Lower multiclass Brier is better. Correct new category means the argmax prediction equals the observed destination among cases where orientation changed; it is not a threshold-free measure of change-risk ranking.

""" + md_table(rows) + """

The combined DPI oil-ENSO model's change-risk ROC AUC is 0.5567, compared with 0.4774 for Markov; its average precision is 0.1280, against a 0.0924 change prevalence. Thus the aggregate proper-score ordering and the change-risk ranking ordering differ. These modest ranking results do not validate reliable anticipation, but zero correct destination choices would not imply zero information in all probabilities.

Four reduced DPI multinomial models correctly select two of 93 changed destinations; all two-hit results occur before 2000. Every evaluated reduced specification selects zero of 60 changed destinations in origins 2000-2022. The original broader six-model analysis likewise selects zero of these 60. Overall accuracy near 90% mainly reflects persistence. The GLI models select zero of 167 changed destinations. Scores from DPI and GLI are not directly comparable because their cases and targets differ.

DPI and aligned GLI HOG disagree in 230 of 1,019 jointly classified observations in 1975-2021 (22.57%). This is conditional on coverage and alignment, not a population-wide error rate. Since GLI partly draws on DPI, the comparison measures source sensitivity. Herre's prior comparison [18] means that source comparison itself is not a first contribution.

The reported covariate models did not outperform the Markov baseline on aggregate multiclass Brier over their respective full evaluation windows. This does not imply that every feature addition worsens every model or period. The results do not prove absence of economic effects, absence of diffusion, statistical equivalence of models or general impossibility of ideological prediction. Country-year dependence, rare transitions, institutional opportunity and label uncertainty require further analysis.
"""
    matrix = "## Closest precedents\n\n" + md_table(nearest) + "\n\n"
    novelty = "## Contribution by dimension\n\n" + md_table(NOVELTY_ROWS) + "\n\n"
    bibliography = "## Verified references and access notes\n\n" + "\n\n".join(
        cite_line(r) + "\n\nReading status: " + r["reading_status"] +
        (". Version note: " + r["note"] if r["note"] else "") + "." for r in REFS)
    report = "\n\n".join([INTRO, matrix, THEMES, novelty, results, PRIORITIES, DRAFT, SEARCH, bibliography])
    (OUT / "LITERATURE_REVIEW.md").write_text(report + "\n")
    (OUT / "MANUSCRIPT_RELATED_WORK.md").write_text(DRAFT + "\n")
    # Fixed source paths and hashes allow review without touching model artifacts.
    paths = ["outputs/extensions/dpi_drivers/metrics.csv", "outputs/extensions/dpi_drivers/metrics_by_period.csv",
             "outputs/extensions/gli_hog/metrics.csv", "outputs/history/history_report.json",
             "outputs/main/metricas.csv", "outputs/main/predicciones_fuera_muestra.csv"]
    (OUT / "provenance.json").write_text(json.dumps(dict(analysis_commit=ANALYSIS_COMMIT,
        review_cutoff=CUTOFF, model_refitted=False,
        source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}), indent=2) + "\n")
    build_pdf(report)
    print(f"Built {len(REFS)}-study review, bibliography, evidence matrix and PDF.")


def build_pdf(markdown):
    from matplotlib.font_manager import findfont
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

    pdfmetrics.registerFont(TTFont("ReviewSans", findfont("DejaVu Sans")))
    pdfmetrics.registerFont(TTFont("ReviewSansBold", findfont("DejaVu Sans:bold")))
    pdfmetrics.registerFontFamily("ReviewSans", normal="ReviewSans", bold="ReviewSansBold")
    styles = {
        "body": ParagraphStyle("body", fontName="ReviewSans", fontSize=9.4, leading=14,
                               spaceAfter=8, textColor=colors.HexColor("#25333D")),
        "h1": ParagraphStyle("h1", fontName="ReviewSansBold", fontSize=21, leading=26,
                             spaceAfter=14, textColor=colors.HexColor("#103D51")),
        "h2": ParagraphStyle("h2", fontName="ReviewSansBold", fontSize=13, leading=17,
                             spaceBefore=13, spaceAfter=8, keepWithNext=True,
                             textColor=colors.HexColor("#103D51")),
        "h3": ParagraphStyle("h3", fontName="ReviewSansBold", fontSize=10.5, leading=14,
                             spaceBefore=8, spaceAfter=6, keepWithNext=True),
        "cell": ParagraphStyle("cell", fontName="ReviewSans", fontSize=8.0, leading=11, alignment=TA_LEFT),
        "head": ParagraphStyle("head", fontName="ReviewSansBold", fontSize=8.0, leading=11,
                               textColor=colors.white),
    }

    def fmt(s):
        s = html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"(https://[^\s]+)", r'<link href="\1" color="#245D86">\1</link>', s)
        return s

    story = []
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("|"):
            raw = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [s.strip() for s in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"[-: ]+", s) for s in cells):
                    raw.append(cells)
                i += 1
            n = len(raw[0])
            width = A4[0] - 96
            if n == 3:
                widths = [width * x for x in (.23, .36, .41)]
            else:
                widths = [width * x for x in (.29, .12, .15, .18, .26)]
            data = [[Paragraph(fmt(c), styles["head" if r == 0 else "cell"]) for c in row]
                    for r, row in enumerate(raw)]
            t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#103D51")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EFF4F6")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 0), (-1, 0), .4, colors.HexColor("#103D51")),
            ]))
            story.extend([t, Spacer(1, 10)])
            continue
        style = "body"
        if line.startswith("### "):
            style, line = "h3", line[4:]
        elif line.startswith("## "):
            style, line = "h2", line[3:]
        elif line.startswith("# "):
            style, line = "h1", line[2:]
        elif line.startswith("- "):
            line = "• " + line[2:]
        # Paragraphs are one line in the authored Markdown; references stay with access notes.
        para = Paragraph(fmt(line), styles[style])
        if line.startswith("[") and re.match(r"\[\d+\]", line):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].startswith("Reading status:"):
                story.append(KeepTogether([para, Paragraph(fmt(lines[j]), styles["body"])]))
                i = j + 1
                continue
        story.append(para)
        i += 1
    target = ROOT / "outputs/literature/Teuken_Literature_and_Novelty_Review.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#B7C7CE"))
        canvas.line(48, 35, A4[0]-48, 35)
        canvas.setFont("ReviewSans", 7)
        canvas.setFillColor(colors.HexColor("#536A75"))
        canvas.drawString(48, 24, "TEUKEN-MARKOV  |  Targeted literature review  |  12 October 2026")
        canvas.drawRightString(A4[0]-48, 24, str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(str(target), pagesize=A4, leftMargin=48, rightMargin=48,
                            topMargin=44, bottomMargin=49, title="Teuken-Markov: Literature and Novelty Review",
                            author="Teuken-Markov research project")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    main()
