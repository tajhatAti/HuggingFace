# Hugging Face policy compatibility guide

Last reviewed against the official [Hugging Face Content Policy](https://huggingface.co/content-policy) on **2026-08-17**. The policy page currently states an effective date of **2025-04-10**.

This guide is an engineering checklist, not legal advice or advance approval from Hugging Face. Context, implementation, data rights, consent, local law, and later policy changes still matter. Hugging Face makes moderation decisions case by case. Recheck the official policy before each material deployment.

## Uses RepoVault will not support

The following list expands the official restricted-content categories into practical examples. A listed item may fit more than one category.

### Illegal, fraudulent, or deceptive activity

1. Content or services that violate applicable law or regulation.
2. Weapons-development instructions for high-risk illegal activity.
3. Illegal-drug manufacturing, trafficking, or procurement services.
4. Scams, advance-fee schemes, or fraudulent giveaways.
5. Unlawful gambling operations or tools that facilitate them.
6. Pseudo-pharmaceutical sales or deceptive medical-product claims.
7. Plagiarism services designed to misrepresent authorship.
8. Phishing pages, credential-harvesting forms, or deceptive login replicas.
9. Deliberate disinformation campaigns or coordinated inauthentic behavior.
10. Fraudulent impersonation intended to deceive or obtain value.
11. Unlawful currency, securities, investment, or transaction schemes.
12. Market manipulation or intentionally deceptive financial promotions.
13. Illegal or unlicensed medical practice.
14. Illegal or unlicensed legal practice.
15. Illegal or unlicensed financial practice.
16. Tools whose primary purpose is evading lawful controls or accountability.

### Harm, abuse, sexual exploitation, or violent extremism

17. Content intended to harm an individual or protected group.
18. Hate speech or discriminatory dehumanization.
19. Harassment, bullying, stalking, or targeted intimidation.
20. Doxxing or publishing private contact/location information without permission.
21. Non-consensual intimate or sexual content.
22. Sexual content used to humiliate, threaten, or harass.
23. Underage nudity.
24. Any sexual content involving minors.
25. Terrorist propaganda, recruitment, or operational support.
26. Content that glorifies violence, suffering, or humiliation.
27. Credible threats or instructions facilitating imminent harm.
28. Abusive synthetic media created without appropriate consent.

### Privacy and intellectual property violations

29. Publishing another person’s physical address without explicit permission.
30. Publishing another person’s private email or phone number without permission.
31. Exposing private credentials, keys, medical records, or financial records.
32. Processing personal data without a valid legal and ethical basis.
33. Copyright-infringing model, dataset, code, image, audio, or text distribution.
34. Trademark or other IP infringement intended to confuse users.
35. Circumvention services whose purpose is unauthorized access to protected content.

### Platform abuse, security violations, and spam

36. Malware, ransomware, trojans, viruses, or malicious payload generation.
37. Tools designed to disrupt, damage, or gain unauthorized system access.
38. Credential theft, session theft, or unauthorized data exfiltration.
39. Unauthorized bot APIs or bot farms.
40. Unauthorized remote-management or remote-control services.
41. Cloudflare Tunnel or similar tunnels used to bypass Space restrictions.
42. TOR, open proxies, or generic proxy relays used to bypass restrictions.
43. VNC, Chrome Remote Desktop/Server, or comparable hosted remote desktops.
44. Hosting excessive or irrelevant repository data.
45. Incentivized manipulation of likes, downloads, trends, or other Hub metrics.
46. Cryptomining or infrastructure primarily supporting cryptomining.
47. Spam advertising, bulk unsolicited activity, or deliberate experience disruption.
48. Resource-exhaustion patterns intended to interfere with Hugging Face services.
49. Authorization bypass for private repositories or protected artifacts.
50. A generic arbitrary-URL fetcher, unrestricted relay, shell, or tunnel disguised as another app.

RepoVault additionally rejects private repositories, visitor credentials, arbitrary hosts, code execution, archive extraction, APK execution, workflow dispatch, and unrestricted large-file proxying even when a hypothetical use might not independently violate policy.

## Illustrative permitted or policy-compatible uses

The official policy defines restricted content rather than pre-approving every other use. The examples below are generally compatible **only when they are lawful, consensual, rights-respecting, transparently described, non-deceptive, properly bounded, and do not become one of the restricted uses above**.

### Open-source and repository productivity

1. Browsing a public repository tree.
2. Discovering public branches and tags.
3. Viewing commit history and changed-file metadata.
4. Previewing bounded public source files.
5. Downloading an exact public Git blob.
6. Packaging selected public files with provenance.
7. Downloading a bounded public source snapshot.
8. Finding APK or AAB files published by their project owner.
9. Reviewing public release notes and assets.
10. Viewing public workflow-run metadata.
11. Linking users to GitHub’s authorized artifact flow.
12. Detecting source languages and file categories.
13. Summarizing repository architecture.
14. Generating a dependency inventory from public manifests.
15. Producing a software bill-of-materials draft.
16. Locating tests, docs, configuration, and CI files.
17. Comparing two public branches defensively.
18. Drafting code-review comments grounded in public evidence.
19. Suggesting maintainability improvements.
20. Creating non-executing static quality reports.
21. Exporting a review as Markdown or JSON.
22. Preparing a user-reviewed patch suggestion.
23. Finding stale documentation references.
24. Explaining an open-source project to a new contributor.
25. Building a read-only public package/release dashboard.

### Responsible AI and machine-learning demonstrations

26. Text classification with properly licensed data.
27. Image classification with consented or licensed images.
28. Speech recognition for user-provided audio.
29. Text-to-speech for lawful, non-deceptive accessibility use.
30. Translation between natural languages.
31. Summarization of user-provided or licensed text.
32. Semantic search over authorized documents.
33. Retrieval-augmented question answering over public documentation.
34. Embedding visualization for educational exploration.
35. Model-card exploration and comparison.
36. Dataset-card browsing and quality reporting.
37. Benchmark visualization with honest methodology.
38. Bias and fairness evaluation using appropriate data.
39. Explainability demonstrations for model outputs.
40. Prompt experimentation with bounded, non-abusive inputs.
41. Synthetic-data generation that respects privacy and IP.
42. OCR for documents the user may lawfully process.
43. Table extraction from authorized documents.
44. Object detection on consented or public-domain images.
45. Image captioning for accessibility.
46. Audio event classification for benign uses.
47. Topic modeling over authorized corpora.
48. Named-entity extraction without publishing private data.
49. Sentiment analysis presented with uncertainty and limitations.
50. Model quantization or inference demonstrations that respect licenses.

### Education and developer learning

51. Interactive programming tutorials.
52. Safe code-explanation tools.
53. Algorithm visualizers.
54. Data-structure demonstrations.
55. Regular-expression learning sandboxes with execution limits.
56. SQL learning against synthetic local data.
57. Git concept tutorials.
58. Public API documentation explorers.
59. Unit-test generation suggestions requiring user review.
60. Lint explanation and style coaching.
61. Defensive secure-coding education.
62. OWASP concept education without unauthorized exploitation.
63. Privacy-engineering checklists.
64. Software-license education.
65. Responsible-AI training materials.
66. Language-learning flashcards.
67. Pronunciation practice with user consent.
68. Math tutoring that explains its work.
69. Physics or chemistry concept visualization for lawful education.
70. Historical-document exploration using licensed sources.
71. Citation-formatting helpers.
72. Reading-comprehension exercises.
73. Public-domain literature analysis.
74. Classroom quiz generation from teacher-provided material.
75. Study planners that avoid deceptive credential claims.

### Accessibility, language, and personal productivity

76. Screen-reader-friendly document conversion.
77. Alt-text drafting for user-owned images.
78. Caption generation for user-provided media.
79. Plain-language rewriting.
80. Dyslexia-friendly text formatting.
81. Color-contrast checking.
82. Keyboard-navigation demonstrations.
83. Meeting-note summarization with participant consent.
84. Personal task organization.
85. Calendar-text parsing without credential collection.
86. Resume formatting using user-provided facts.
87. Cover-letter drafting without impersonation or false claims.
88. Grammar and spelling assistance.
89. Tone rewriting that remains non-deceptive.
90. Multilingual glossary generation.
91. Offline-first note categorization.
92. Public-document search and bookmarking.
93. File-name and folder-structure organization suggestions.
94. Accessible chart descriptions.
95. Form readability and usability review.

### Science, civic information, and public benefit

96. Visualization of open scientific datasets.
97. Reproducibility checklists for published research.
98. Literature mapping over licensed abstracts.
99. Climate-data visualization from authoritative sources.
100. Biodiversity image classification with appropriate data rights.
101. Astronomy image exploration.
102. Open geospatial-data visualization that avoids exposing sensitive individuals.
103. Public-transit schedule exploration.
104. Disaster-preparedness education from authoritative guidance.
105. Public-law and regulation search that clearly disclaims legal advice.
106. Government open-data dashboards.
107. Election-information tools using authoritative sources without manipulation.
108. Accessibility audits for public websites.
109. Non-diagnostic wellness education with appropriate disclaimers.
110. Food and nutrition reference tools that avoid unlicensed medical claims.
111. Environmental sensor dashboards.
112. Energy-efficiency calculators with transparent assumptions.
113. Research metadata cleaning.
114. Scientific unit conversion.
115. Citation-network visualization.

### Creative, media, and community tools

116. Generating original non-infringing artwork.
117. Editing user-owned images.
118. Creating icons and diagrams from lawful prompts.
119. Story brainstorming without copying protected works.
120. Poetry and writing assistance.
121. Music metadata organization without redistributing copyrighted audio.
122. Podcast transcript search for authorized recordings.
123. Subtitle translation for content the user may process.
124. Public-domain archive exploration.
125. Color-palette generation.
126. Typography pairing suggestions.
127. Layout and wireframe ideation.
128. Game-design brainstorming that does not facilitate gambling abuse.
129. Community FAQ assistants grounded in approved documents.
130. Moderation-assistance tools with human review and transparent rules.

### Business and operations utilities

131. Inventory dashboards using authorized business data.
132. Product-catalog search.
133. Customer-support draft generation with human review.
134. FAQ retrieval from official company documentation.
135. Contract-clause organization that clearly avoids legal advice.
136. Invoice data extraction from user-owned documents.
137. Expense categorization without deceptive financial claims.
138. Forecast visualization with uncertainty disclosures.
139. Survey analysis using consented responses.
140. Anonymized feedback clustering.
141. Quality-assurance checklists.
142. Incident postmortem formatting.
143. Status-page summarization.
144. Documentation migration assistance.
145. Localization workflow support.
146. Brand-style consistency checking on authorized materials.
147. Public changelog generation.
148. Release-note drafting from verified commits.
149. Read-only observability dashboards that expose no secrets.
150. Bounded data-format conversion for files the user is allowed to process.

## RepoVault-specific deployment decision

RepoVault is designed to stay on the compatible side of these boundaries:

- public GitHub data only;
- read-only, non-executing, and non-extracting behavior;
- exact commit/blob identity;
- validated official GitHub API and codeload hosts only;
- no visitor token, private-repository access, shell, tunnel, proxy, or remote management;
- bounded branches, trees, blobs, ZIPs, temporary storage, caches, queues, prompts, and model output;
- GitHub authorization remains mandatory for protected Actions artifacts;
- complete source archives are streamed to private ephemeral disk, validated, served through the Space, and automatically expired;
- generated reviews are advisory and require human judgment.

Before deployment, run the tests in `docs/OPERATIONS.md`, inspect the current official policy and Terms, and verify that no new feature changes these boundaries.
