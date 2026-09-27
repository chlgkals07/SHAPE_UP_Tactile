# Tactile Sensors for LEAP Hand Dexterous Manipulation

## 1. Executive Summary

**For this project, I would prioritize PaXini distributed tactile sensors, XELA uSkin, and GelSight Mini—in that order under your evidence hierarchy.** They serve different purposes:

- **PaXini:** strongest direct evidence from LEAP tactile-conditioned policy learning.
- **XELA uSkin:** strongest documented, integrated LEAP sensing package, with substantial learning research on Allegro.
- **GelSight Mini:** strongest verified commercial optical option for LEAP contact-geometry research, with important speed and mechanical limitations.

**The central procurement uncertainty is PaXini’s exact research configuration.** The strongest LEAP papers identify PaXini and describe their arrays, but do not provide an unambiguous current orderable part number. A current PX-6AX product should not automatically be treated as identical to those research sensors.

This survey followed three search passes: **LEAP-first literature discovery; sensor-to-paper searches; and citation/project/repository follow-up**. The principal Top-3 sources were subsequently reopened to verify hardware configurations. Sources and purchasing information were checked on **25 September 2026**.

The evidence does **not** support a controlled, sensor-versus-sensor performance ranking. The recommendations below reflect research relevance and implementation evidence, not a meta-analysis of incomparable success rates.

### Overall Top 3

| Rank | Candidate | Strongest LEAP evidence | Best fit for this project | Principal reservation |
|---|---|---|---|---|
| **1** | **PaXini distributed tri-axis sensors / PX-6AX family** | Real LEAP policy learning in **3DTacDex**, **AdapTac**, and a newer cluttered-grasping study | Distributed contact representation, tactile-conditioned imitation learning, force-aware manipulation | Exact paper hardware versus current commercial SKU must be confirmed |
| **2** | **XELA uSkin LEAP package** | **Official LEAP integration**; strong Allegro tactile-learning literature | Whole-hand contact sensing, grasp stabilization, tactile/proprioceptive policies | I did **not** verify a LEAP algorithm paper using this package |
| **3** | **GelSight Mini** | Real LEAP cable-following paper; additional LEAP imitation-learning thesis | Contact geometry, deformation, tactile embeddings, slower precision manipulation | Optical packaging and a reported **>70 ms depth-image delay** in the LEAP implementation |

Primary evidence: [3DTacDex](https://arxiv.org/html/2409.17549v2), [AdapTac](https://arxiv.org/html/2505.13982v1), [XELA LEAP integration](https://xelarobotics.com/products/for-leap-hand/), [LEAP cable following](https://arxiv.org/html/2403.12676v2).

### High-End Shortlist

| Option | Why consider it without a budget constraint? | Recommended purchasing approach |
|---|---|---|
| **XELA uSkin, integrated LEAP configuration** | Documented whole-hand integration and established software; minimizes sensor-development work | Request an assembled package, individual calibration, replacement skins, and latency documentation |
| **PaXini, research-matched LEAP configuration** | Most relevant demonstrated LEAP learning infrastructure | Obtain the exact sensor geometry, electronics, API, calibration, and mounts used by a reference research group |
| **GelSight Mini as a complementary subsystem** | Adds detailed local geometry that sparse force arrays do not directly provide | Start with thumb/index sensing for a geometry-focused experiment |

**My practical recommendation:** contact PaXini and XELA in parallel. Prefer PaXini if the published LEAP configuration is reproducibly obtainable; prefer XELA if PaXini cannot resolve the hardware/API uncertainty. Add optical sensing only when contact geometry is central to the experiment.

---

## 2. What LEAP Hand Researchers Actually Use

### LEAP Hand + tactile sensing papers

**Evidence notation**

- **A—policy:** real LEAP autonomous manipulation with tactile input.
- **A—control:** real LEAP tactile-feedback control, without a learned policy.
- **A—demo:** research mounting, teleoperation, or hardware demonstration; weaker evidence for autonomous policy learning.
- **B:** official commercial LEAP integration.
- **NR:** not reported or not confirmed in accessible primary material.

“Original-form LEAP” below means the conventional four-finger, 16-DoF configuration; a precise hardware revision is often omitted.

| Paper | Year / venue | LEAP version | Tactile sensor | Placement | Sensors / taxels | Task | Tactile representation | Policy/model | Key result / evidence |
|---|---|---|---|---|---|---|---|---|---|
| [Canonical Representation and Force-Based Pretraining… — 3DTacDex](https://arxiv.org/html/2409.17549v2) | ICRA 2025 | Original-form, 16 DoF | PaXini | Tip and finger pad on every finger | **8 modules; 120 tri-axis taxels** | Box opening, reorientation, cap flipping, assembly | Force plus canonical spatial features | Pretrained graph encoder + diffusion policy | **78% vs 53%** vision-only average; A—policy |
| [Adaptive Visuo-Tactile Fusion… — AdapTac](https://arxiv.org/html/2505.13982v1) | IROS 2025 | Original-form, 16 DoF | PaXini | Tips and pads | **8 × 15 taxels** | Box opening, cup reorientation, sponge flipping | Spatial force features and visual point clouds | Force-guided attention + diffusion policy | **93% vs 73%** vision-only average; A—policy |
| [When Does Touch Matter? Charting the Vision–Interaction Gap in Cluttered Dexterous Grasping](https://arxiv.org/html/2609.24068v1) | September 2026 preprint | 16 DoF | PaXini | Four fingertips | **508 tri-axis taxels total** | Cluttered grasping | Taxel positions/forces; separate estimated wrench observations | Attention encoder + diffusion policy | 24/25 successes with combined signals vs 14/25 vision; A—policy, very recent |
| [In-Hand Following of Deformable Linear Objects Using Dexterous Fingers with Tactile Sensing](https://arxiv.org/html/2403.12676v2) | IROS 2024 | Original-form | GelSight Mini | Thumb and index | **2 cameras/sensors** | Following cables through the fingers | Depth/contact geometry + forward kinematics | Contact segmentation, line fitting, hybrid position/force control | Real tactile closed-loop manipulation; A—control |
| [A Dexterous Multi-Finger Robotic Manipulator Framework…](https://pure.unileoben.ac.at/en/publications/a-dexterous-multi-finger-robotic-manipulator-framework-for-intuit/) | 2025 master’s thesis | LEAP; revision NR | GelSight Mini | Exact count/placement not confirmed from accessible abstract | NR | Contact-rich imitation learning | Learned visual/tactile features | BYOL/MViTac/ResNet-based comparisons | Institutional evidence of real LEAP learning; thesis-level |
| [Feeling the Future: Dexterous Bolt Manipulation in Robotics Using Optical Tactile Sensing](https://theses-dissertations.princeton.edu/entities/publication/270fe74d-920c-4efd-988f-675149fe98ae) | 2026 senior thesis | **Three-finger redesign** | DIGIT | Two fingers | **2 sensors** | Bolt seeking/alignment | Reduced contact features + robot state | Demonstration learning; threading classifier | Lower validation loss, not proof of fourfold real task success |
| [ViHaTeleop: A Low-Cost, Lightweight Visual-Haptic Teleoperation System for Dexterous Manipulation Learning](https://arxiv.org/html/2608.16572v1) | August 2026 preprint | 16 DoF | 9DTact | Thumb, index, middle | **3 sensors** | Haptic teleoperation; manipulation demonstrations | Deformation-derived feedback | Retargeting + human haptic loop | Real LEAP hardware; downstream learning comparisons are **simulation**, A—demo |
| [Blind Dexterous Grasping via Real2Sim2Real Tactile Policy Learning](https://arxiv.org/html/2606.11767v1) | June 2026 preprint | LEAP | Custom curved TwinTac + FSRs | Four tips; links and palm | **32 pressure channels + 12 FSRs** | Vision-free grasping | **44 binarized contact channels** | RL experts distilled into diffusion policy | **27% real success vs 6% without calibration**; A—policy |
| [AURORA: Active Uncertainty-Driven Re-Orientation for In-Hand Reconstruction](https://arxiv.org/html/2609.08493v1) | September 2026 preprint | Modified fingertips | FSRs | Tips, inner links, palm | **16 scalar sensors** | Reorientation for visual reconstruction | Binary contacts | Tactile/proprioceptive low-level RL | Contact baseline; not rich distributed sensing |
| [The MOTIF Hand…](https://arxiv.org/html/2506.19201v1) | 2025 preprint | LEAP-derived | Resistive tactile arrays plus other modalities | Finger pads | **6 × 6 per array**; total count not independently confirmed | Multimodal grasp observation | Pressure maps, thermal and inertial signals | Observation/estimation framework | No isolated pressure-policy benefit established |
| [AnySkin: Plug-and-play Skin Sensing for Robotic Touch](https://arxiv.org/html/2409.08276v3) | ICRA 2025 | LEAP pictured in hardware demonstration | AnySkin | Custom skin mounting | Benchmark configuration differs | Hardware adaptability | Raw magnetic readings | Main learning experiments use grippers | **LEAP fit evidence, not a LEAP policy benchmark** |
| [Bio-Skin project](https://williamalexanda.github.io/Bio-Skin/) | Paper: IROS 2025; project updated separately | LEAP demonstration | Bio-Skin | Four fingertips shown | Multimodal fingertip modules | Hardware demonstration | Normal/shear/temperature signals | LEAP policy details NR | Paper experiments and later LEAP project demonstration must be distinguished |
| [Demonstrating LEAP Hand v2…](https://www.roboticsproceedings.org/rss21/p132.pdf) | RSS 2025 demonstration | **LEAP v2** | FSR | Fingers | One scalar sensor per finger | Low-cost tactile capability | Scalar force-related readings | Hardware demonstration | Useful inexpensive baseline |

Two additional leads should **not** be silently promoted into fully documented LEAP policy evidence:

- **DenseTact:** a [Stanford dissertation-defense description](https://events.stanford.edu/event/won-kyung-do-phd-defense-improving-robotic-dexterity-with-optical-tactile-sensor-densetact) explicitly mentions LEAP integration. However, I could not establish a complete paper-level LEAP configuration for the related TensorTouch system.
- **DexMani:** its [official project](https://dexmani.github.io/) describes LEAP rotation with TwinTac. Treat it as emerging project evidence until the full hardware and experimental record can be inspected.

### Patterns in this literature

**Distributed force sensing currently has the clearest LEAP policy-learning evidence.** The PaXini studies preserve spatial contact information rather than reducing touch to one contact bit per finger.

**Most strong results are visuotactile.** They do not directly establish performance for a policy restricted to:

\[
o_t=[q_t,\dot q_t,T_t].
\]

That is a useful research opportunity: evaluate tactile/proprioceptive manipulation after initial acquisition, with external vision removed from the policy.

**Coverage and representation matter together.** AdapTac reports that naïvely incorporating tactile features can underperform vision alone. More channels do not automatically produce a better policy. Its paper and project also report different unseen-object evaluations: the [updated project explicitly corrects that evaluation](https://adaptac-dex.github.io/). Those results should not be combined as one experiment.

---

## 3. Candidate Landscape

### Commercial / ready-to-buy

| Candidate | Assessment |
|---|---|
| **XELA uSkin LEAP package** | Most clearly documented integrated commercial LEAP option |
| **PaXini PX-6AX family** | Current commercial family with strong related LEAP research; research-matched package requires confirmation |
| **GelSight Mini** | Purchasable complete sensor; LEAP mounts still required |
| **DIGIT** | Purchasable complete optical sensor; established manipulation ecosystem |
| **WowSkin** | Commercial AnySkin-derived option; stock, package contents, and LEAP adapter availability need confirmation |

“Ready-to-buy” does not mean “ready-to-run on LEAP.” Mounts, interfaces, calibration, and software synchronization remain part of the system.

### Commercial + custom integration

- PaXini, unless a complete matching LEAP package is supplied.
- Standalone uSkin modules outside the official LEAP package.
- GelSight Mini and DIGIT using custom fingertip adapters.
- Commercial resistive arrays, such as Tekscan, with custom coverings and electronics.
- BioTac-family sensors on a substantially redesigned fingertip; no verified LEAP integration found.

### Fabrication required

- **AnySkin**, when assembled from its research design.
- **ReSkin** and derivative palm/finger skins.
- **eFlesh**.
- **TwinTac**, **Bio-Skin**, and many DenseTact/TensorTouch configurations.
- **9DTact**, if using the open fabrication route instead of a supplier-built unit.

### Vision-based tactile

The important options are **GelSight Mini, DIGIT, 9DTact, DenseTact, and TensorTouch**.

They provide local appearance and deformation observations from which geometry, force, or slip can be inferred. They do **not** intrinsically provide calibrated distributed pressure simply because their images have many pixels.

For LEAP, their principal tradeoff is detailed local contact information versus **fingertip volume, USB routing, image processing, and latency**.

---

## 4. Detailed Sensor Comparison

**P = paper-reported; M = manufacturer-reported.**  
“Not publicly specified” means no reliable configuration-specific value was confirmed. Rates refer to different stages and should not be compared as interchangeable measures of latency.

| Sensor | Principle | Purchase / fabrication | LEAP evidence | Spatial sensing | Shear | Output | Sampling rate | Size | Raw data | SDK | ROS | Integration effort | Price | Representative papers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **PaXini PX-6AX family** | Magnetic elastomer / distributed force estimation | Commercial; custom integration or quoted package | **A—policy**; exact SKU unresolved | 15 taxels/module in two main LEAP studies; other configurations differ | Tri-axis taxel force estimates | \(N\times3\), optional derived wrench | Current family advertises up to **1,000 Hz output** M; LEAP policies ran **5 Hz** P | Model-dependent; research module envelope NR | Per-taxel data used in research; underlying magnetic access NR | Research acquisition exists; commercial API terms verify | Maintained public package not confirmed | Medium unless supplied integrated | **Quote required** | P1–P4 |
| **XELA uSkin LEAP** | Magnetic distributed sensing | Integrated commercial package | **B**; research on Allegro | **368 taxels**, fingertips/links/palm M | Yes | Tri-axis signals/forces; temperature | **Up to 220 Hz full-hand** M | LEAP-specific curved tips and patches | Raw and calibrated access advertised | Python/C++; uAI | ROS/ROS2 advertised | Low–medium | **Quote required** | X1–X3 |
| **AnySkin** | Magnetized elastomer over magnetometers | Fabricate or purchase compatible components | **A—demo**, not LEAP learning benchmark | Standard design: **5 magnetometers / 15 values** | Shear-sensitive magnetic signal; force needs calibration | \(5\times3\) magnetic readings | **100 Hz** in learning studies P | Approximately **2 mm skin**; total package depends on PCB/mount | Yes | Open Python/software | Core ROS package not verified | Medium | Complete current system cost not established | A1–A2 |
| **WowSkin** | Commercial AnySkin-derived magnetic skin | Commercial listing | **B claim:** vendor describes LEAP structural parts | Exact purchased configuration verify | Magnetic shear sensitivity; calibration verify | Magnetic signals | Configuration-specific rate not confirmed | Variant-dependent | Vendor software exposes readings; protocol completeness verify | Public MIT-licensed software | Not confirmed | Potentially low; stock/adapter uncertainty | **$128 displayed standard variant**, availability ambiguous | No independent WowSkin papers found |
| **eFlesh** | Magnets in printed compliant microstructures | TPU printing, magnets, PCB | No verified LEAP study | Five-magnetometer research configuration; geometry customizable | Shear-sensitive | Raw magnetic features or learned estimates | **100 Hz** P | Custom | Yes | Open design/code | Not confirmed | Medium–high | Full BOM not established; **“<$5” is not a complete-sensor price** | E1 |
| **ReSkin** | Magnetic elastomer | Casting, electronics, often pulse magnetization | No verified LEAP manipulation paper | Layout-dependent | Yes, through magnetic response/calibration | \(N\times3\) magnetic values | **30 Hz D’Manus; 78 Hz palm study** P | Custom; examples use thin skins | Yes | Open | Not uniform across projects | High | Configuration-specific BOM | R1–R3 |
| **GelSight Mini** | Camera images of illuminated elastomer | Commercial sensor + adapter | **A—control**, additional thesis | Dense contact images/depth | Inferred through markers/deformation/model | RGB; reconstructed depth/point cloud | **25 FPS** M; LEAP depth delay **>70 ms** P | **18.6 × 14.3 mm field of view** M; not housing size | Yes | `gsrobotics`, Python | Integration support should be confirmed | Medium | **$510 system / $560 robotics package** | G1–G3 |
| **DIGIT** | Optical elastomer | Commercial sensor + adapter | LEAP redesign thesis; stronger Allegro evidence | Dense images | Inferred, not native calibrated taxel force | RGB; learned depth/features | Original paper: **640×480 at 60 FPS**; studies also use 30 Hz | Original paper: **20×27×18 mm**, 20 g | Yes | `digit-interface` | Wrappers exist; supported package verify | Medium | **$355** | D1–D4 |
| **9DTact** | Optical deformation/intensity | DIY or supplier-built | **A—demo**, real LEAP teleoperation | Dense image/depth | Learned net 6D wrench; not independent shear per pixel | Images, shape, estimated wrench | LEAP system **20 Hz**; camera maximum not verified | Not confirmed here | Yes | Open code | Repository includes ROS shape/force code | Medium–high | Supplier quote / current price unverified | N1–N2 |
| **TwinTac** | MEMS pressure beneath elastomer | PCB, molding, electronics | **A—policy** | **8 pressure channels per fingertip** | No demonstrated calibrated distributed shear | Pressure; binarized in LEAP policy | **55 Hz** original 8-channel sensor P | Custom curved LEAP version | Yes | Research code | Not confirmed | High | Complete system cost not established | T1–T2 |
| **Bio-Skin** | Hall, piezoresistive and thermal components | Multilayer fabrication | LEAP project demonstration; paper uses other hand | Multimodal fingertip measurements | Separate shear-sensitive elements | Normal/shear/temperature | Not confirmed for LEAP | Custom | Research design | Research code/design | Not confirmed | High | Complete LEAP BOM not established | B1 |
| **DenseTact / TensorTouch** | Curved optical elastomer | Custom fabrication and calibration | LEAP research mention; exact configuration unresolved | Dense deformation/contact fields | TensorTouch estimates stress components | Images, geometry, learned stress | Configuration-dependent | Multiple distinct prototypes | Yes in research | Project code/design varies | Configuration-dependent | High–very high | Complete procurement cost unavailable | C1–C3 |
| **FSR baseline** | Resistive scalar contact/force response | Commercial components + wiring | Multiple direct LEAP implementations | One value per element | No | Scalar / binary contact | Electronics-dependent | Small, geometry-dependent | Yes | Simple acquisition | Custom | Low–medium | Low component cost; see §9 | LEAP v2, AURORA |

Primary hardware/software sources: [PaXini GEN3](https://www.paxini.com/news/ax/gen3), [GEN4](https://www.paxini.com/cn/ax/gen4), [XELA LEAP](https://xelarobotics.com/products/for-leap-hand/), [XELA uAI](https://xelarobotics.com/uai-software/), [AnySkin](https://github.com/raunaqbhirangi/anyskin), [WowSkin](https://shop.wowrobo.com/products/enhanced-anyskin-premium-crafted-editionwowskin), [eFlesh](https://e-flesh.com/), [ReSkin](https://reskin.dev/), [Mini specification sheet](https://www.gelsight.com/wp-content/uploads/productsheet/Mini/GS_Mini_4.3.24.pdf), [GelSight store](https://www.gelsight.com/online-store/), [9DTact repository](https://github.com/linchangyi1/9DTact).

---

## 5. Sensor-by-Sensor Analysis

### PaXini: strongest direct LEAP learning evidence

The important evidence is **not** its advertised sensitivity. It is that multiple researchers have used spatial tri-axis observations on LEAP for real manipulation.

Its main advantage is a representation naturally suited to contact-state learning: contact location, force direction, and interactions between fingers. The 3DTacDex and AdapTac implementations provide particularly relevant starting points, including [policy code](https://github.com/tianhaowuhz/3dtacdex) and [AdapTac code](https://github.com/kingchou007/adaptac-dex).

**Limitations**

- Research modules and current generations cannot yet be matched confidently.
- Maximum output frequency is not a verified synchronized full-LEAP rate.
- Manufacturer “spatial resolution” should not be interpreted as taxel pitch.
- Magnetic/elastomer responses need calibration and can exhibit coupling.

An independent insertion paper documents nonuniformity, cross-instance differences, and spurious shear in an **older GEN1 model**. That is useful negative evidence, but not proof that current models have identical errors. [P4](https://arxiv.org/html/2505.02915v2)

Current manufacturer pages advertise different sensitivity thresholds—**0.01 N for GEN3 versus 0.005 N for GEN4**—and laboratory durability/range claims. These are generation-specific specifications, not independently established performance on LEAP. [GEN3](https://www.paxini.com/news/ax/gen3), [GEN4](https://www.paxini.com/cn/ax/gen4)

### XELA uSkin: strongest integrated infrastructure option

XELA’s appeal is a coherent hand-level system rather than a loose set of sensing modules. Its official package covers fingertips, intermediate contact surfaces, and palm.

The research ecosystem is also directly relevant: representation pretraining, residual reinforcement learning, and spatial/temporal tactile encoders have all been demonstrated using uSkin on Allegro.

**Limitations**

- Those Allegro results do not constitute LEAP policy validation.
- Calibration and magnetic compensation matter.
- A tactile array’s mechanical compliance changes contact behavior.
- “Shear sensing” does not mean a validated incipient-slip classifier is included.

The current software page lists slip detection as **“Coming Soon.”** Buy the sensing capability on its documented merits; do not budget around an already delivered turnkey slip classifier. [XELA software](https://xelarobotics.com/uai-software/)

### GelSight Mini: best-supported LEAP optical choice

Mini is attractive when the research depends on **local geometry, cable orientation, contact shape, or deformation**, rather than only force direction.

The LEAP cable-following project provides a concrete starting point, including [hardware/code resources](https://github.com/Mingrui-Yu/DLO_following). Its geometry-driven feedback is useful evidence even though it is not a learned dexterous policy.

**Limitations**

- The LEAP paper reports depth-image arrival delays above 70 ms on its implementation.
- Camera housing and adapters alter fingertip geometry.
- Gel wear and surface condition change observations.
- Depth reconstruction is not calibrated pressure or shear force.

The official software documentation also states that Mini is not a metrology instrument with a quantified universal measurement accuracy. [Mini software and FAQ](https://github.com/gelsightinc/gsrobotics)

### AnySkin: strong low-dimensional learning platform, weaker LEAP validation

AnySkin offers open raw signals and replaceable sensing material. Its demonstrated strength is learning directly from uncalibrated magnetic observations while reducing sensitivity to skin replacement.

However, the distinction matters:

**The paper shows LEAP adaptability; the substantive learning benchmarks use grippers.**

It is therefore a strong prototype or secondary option, but not better supported than PaXini or XELA for this specific hand.

Known concerns include magnetic interference, remaining skin-to-skin variation, and the difference between raw magnetic features and physical force measurements. [AnySkin paper](https://arxiv.org/html/2409.08276v3)

### WowSkin: potentially convenient, evidence currently vendor-led

WowSkin may reduce AnySkin fabrication burden. The vendor describes LEAP structural integration, and software is [publicly available](https://github.com/WowRobo-Robotics/WowSkin).

I did not find independent papers establishing that a purchased WowSkin unit reproduces AnySkin’s reported learning or replacement-transfer results. **AnySkin papers should not be listed as direct WowSkin adoption.**

The product page also presents ambiguous availability signals. Treat it as a procurement lead requiring confirmation, not an assured immediately available LEAP kit.

### eFlesh: particularly interesting for a hardware extension

eFlesh replaces cast magnetic skin with printed compliant structures and inserted magnets. This makes geometry and mechanical response part of the design space.

It is attractive for testing how fingertip compliance or internal structure affects tactile representations. It is less attractive when the objective is to avoid hardware development.

Its paper demonstrates real gripper manipulation and slip-related learning, but I found no verified LEAP implementation. The frequently repeated **“<$5” concerns magnets, not the complete sensor**. [eFlesh paper](https://arxiv.org/html/2506.09994v1)

### ReSkin: flexible research platform with substantial engineering burden

ReSkin is well suited to large or unusual sensing surfaces, including the palm. Its strongest relevance here is the Allegro study that learns in-hand translation using both normal and shear-related information.

The cost is fabrication and system identification: elastomer processing, magnetization, PCB layout, attachment, calibration, and replacement consistency.

The translation study also changes surface friction with a thin PET layer to make manipulation mechanically feasible. That is a useful reminder that **skin mechanics can dominate the learning problem**. [In-hand translation paper](https://arxiv.org/html/2407.07885v1)

### DIGIT: substantial dexterous-manipulation ecosystem, less direct LEAP evidence

DIGIT has persuasive Allegro evidence for tactile dynamics and object-state estimation, plus a major software/representation ecosystem.

The verified LEAP evidence found here is a thesis using a **three-finger redesign**, not a standard four-finger deployment with a mature public benchmark. Its lower purchase price does not erase that integration distinction.

Also distinguish **DIGIT from DIGIT360**: they are different hardware platforms. Results using DIGIT360 should not be attributed to the purchasable original DIGIT.

### 9DTact: promising direct LEAP mounting evidence

9DTact offers open construction, shape reconstruction, and learned wrench estimation. ViHaTeleop strengthens its LEAP relevance through a three-fingertip real deployment.

However, that paper’s downstream policy comparisons are simulated. It does not yet provide the same autonomous real-LEAP learning evidence as PaXini.

### TwinTac and Bio-Skin: useful custom-system candidates

**TwinTac** has direct LEAP policy use, but its signals were binarized. The result supports its utility for contact coverage and calibrated simulation, not a claim of rich force-vector perception.

**Bio-Skin** combines modalities that could be valuable for material interaction, but requires custom fabrication. Its later LEAP demonstration should be distinguished from its paper’s main robot experiments.

### DenseTact / TensorTouch: high-value research, high engineering commitment

This family addresses curved contact coverage and dense deformation/stress estimation. TensorTouch is especially relevant if recovering distributed shear becomes a secondary contribution.

Its calibration workflow uses substantial instrumentation and modeling. It is not a practical substitute for ordering a supported sensor when manipulation learning is the main research contribution. [TensorTouch](https://arxiv.org/html/2506.08291v1)

---

## 6. Representative Papers

The entries below distinguish **actual sensor adoption** from related-family work. Where fewer than three qualifying papers were found, that is stated rather than filling the list with weak matches.

### PaXini — four relevant papers

**P1. Canonical Representation and Force-Based Pretraining of 3D Tactile for Dexterous Visuo-Tactile Policy Learning.**  
Tianhao Wu, Jinzhou Li, Jiyao Zhang, Mingdong Wu, Hao Dong. **ICRA 2025.** [Paper](https://arxiv.org/html/2409.17549v2)

Real LEAP/JAKA setup; tip/pad arrays. Graph-based force pretraining feeds a visuotactile diffusion policy. Matched vision-only and representation ablations demonstrate benefit; ten trials per task limit precision. See §2 for configuration and results.

**P2. Adaptive Visuo-Tactile Fusion with Predictive Force Attention for Dexterous Manipulation.**  
Jinzhou Li, Tianhao Wu, Jiyao Zhang, Zeyuan Chen, Haotian Jin, Mingdong Wu, Yujun Shen, Yaodong Yang, Hao Dong. **IROS 2025.** [Paper](https://arxiv.org/html/2505.13982v1)

Real LEAP/Flexiv system. Predictive force features guide fusion with visual point clouds. Both modality and fusion comparisons are provided. A naïve tactile-concatenation baseline achieves only 40% average success, illustrating that tactile observations require suitable modeling.

**P3. When Does Touch Matter? Charting the Vision–Interaction Gap in Cluttered Dexterous Grasping.**  
Hao Jiang, Luis Dominguez, Daniel Seita. **2026 arXiv preprint.** [Paper](https://arxiv.org/html/2609.24068v1)

Real LEAP/xArm7, four high-density tactile fingertips. An attention encoder processes position/force tokens for diffusion learning. Vision, taxels, estimated wrenches, and combinations are compared: 14/25, 18/25, and 24/25 successes for vision, vision-plus-taxels, and the combined system respectively. Very recent and small-scale.

**P4. Zero-shot Sim2Real Transfer for Magnet-Based Tactile Sensor on Insertion Tasks.**  
Beining Han, Abhishek Joshi, Jia Deng. **2025 preprint; updated 2026.** [Paper](https://arxiv.org/html/2505.02915v2)

**Not LEAP:** FR3 with two custom gripper fingers and **PX6AX-GEN1-PAP-L4629** pads. CNN tactile histories support asymmetric SAC transfer. Real insertion averages 80%, versus 15% without tactile and 33% with binarized tactile. Particularly useful for its sensor-error analysis and continuous-versus-binary comparison.

### XELA uSkin — three strong dexterous-learning papers

**X1. Dexterity from Touch: Self-Supervised Pre-Training of Tactile Representations with Robotic Play.**  
Irmak Guzey, Ben Evans, Soumith Chintala, Lerrel Pinto. **CoRL 2023.** [Proceedings](https://proceedings.mlr.press/v229/guzey23a.html), [paper](https://arxiv.org/html/2303.12076v1)

Real Allegro with fifteen 4×4 tri-axis pads. Signals become a padded tactile image for BYOL pretraining and nearest-neighbor imitation. Demonstrates downstream benefit from tactile play representations; explicitly discusses uncalibrated sensing, hysteresis, and magnetic interference.

**X2. See to Touch: Learning Tactile Dexterity through Visual Incentives.**  
Irmak Guzey, Yinlong Dai, Ben Evans, Soumith Chintala, Lerrel Pinto. **ICRA 2024.** [Paper](https://arxiv.org/html/2309.12300v1)

Real Allegro/Jaco, fifteen uSkin pads. A pretrained tactile encoder supports residual reinforcement learning, with visual imitation rewards. Includes tactile-related comparisons across dexterous tasks. This is evidence for tactile-conditioned learning on another hand, not direct LEAP validation.

**X3. Self-supervised Perception for Tactile Skin Covered Dexterous Hands.**  
Akash Sharma, Carolina Higuera, Chaithanya Krishna Bodduluri, Zixi Liu, Taosha Fan, Tess Hellebrekers, Mike Lambeta, Byron Boots, Michael Kaess, Tingfan Wu, Francois Robert Hogan, Mustafa Mukadam. **CoRL 2025.** [Proceedings](https://proceedings.mlr.press/v305/sharma25a.html), [paper](https://arxiv.org/html/2505.11420v1)

Real Allegro/Franka with eighteen pads totaling 368 taxels. A spatial/temporal transformer uses magnetic histories and taxel positions. Evaluates perception and downstream insertion learning. Especially relevant to full-hand representations rather than flattening all channels.

### GelSight Mini — three directly relevant sources

**G1. In-Hand Following of Deformable Linear Objects Using Dexterous Fingers with Tactile Sensing.**  
Mingrui Yu, Boyuan Liang, Xiang Zhang, Xinghao Zhu, Lingfeng Sun, Changhao Wang, Shiji Song, Xiang Li, Masayoshi Tomizuka. **IROS 2024.** [Paper](https://arxiv.org/html/2403.12676v2)

Real LEAP/FANUC system. Two Mini sensors provide geometry for cable-following control. Comparison with a parallel-gripper approach is informative, but not a clean learned-policy tactile/no-tactile ablation. Its latency and kinematic limitations are unusually relevant to integration.

**G2. A Dexterous Multi-Finger Robotic Manipulator Framework for Intuitive Teleoperation and Contact-Rich Imitation Learning.**  
Clemens Fritze. **2025 master’s thesis, Montanuniversität Leoben.** [Institutional record](https://pure.unileoben.ac.at/en/publications/a-dexterous-multi-finger-robotic-manipulator-framework-for-intuit/)

Real LEAP, Franka Panda, Mini sensing, and Quest-based teleoperation. Compares representation approaches for contact-rich imitation. The accessible institutional abstract supports the system identification; exact sensor count and detailed ablations were not independently recoverable. Treat as weaker evidence than G1.

**G3. Sparsh: Self-supervised Touch Representations for Vision-Based Tactile Sensing.**  
Carolina Higuera, Akash Sharma, Chaithanya Krishna Bodduluri, Taosha Fan, Patrick Lancaster, Mrinal Kalakrishnan, Michael Kaess, Byron Boots, Mike Lambeta, Tingfan Wu, Mustafa Mukadam. **CoRL 2024.** [Paper](https://openreview.net/forum?id=xYJn2e1uu8), [repository](https://github.com/facebookresearch/sparsh)

Uses multiple optical sensor datasets, including Mini and DIGIT. Self-supervised encoders support force, slip, and other tactile tasks. Mini force/slip data and inference examples are available. This supports representation infrastructure; it is not a Mini-on-LEAP policy demonstration.

A foundational reference is **GelSight: High-Resolution Robot Tactile Sensors for Estimating Geometry and Force**, Wenzhen Yuan, Siyuan Dong, Edward H. Adelson, **Sensors 2017**. It describes the broader technology, not adoption of the later commercial Mini. [Paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC5751610/)

### AnySkin — two verified core papers

**A1. AnySkin: Plug-and-play Skin Sensing for Robotic Touch.**  
Raunaq Bhirangi, Venkatesh Pattabiraman, Enes Erciyes, Yifeng Cao, Tess Hellebrekers, Lerrel Pinto. **ICRA 2025.** [Paper](https://arxiv.org/html/2409.08276v3)

Real gripper experiments use five magnetometers and replaceable skin. Temporal magnetic features support slip detection; learned policies are tested across skin changes. The LEAP illustration establishes adaptability, not an autonomous LEAP benchmark.

**A2. Learning Precise, Contact-Rich Manipulation through Uncalibrated Tactile Skins.**  
Venkatesh Pattabiraman, Yifeng Cao, Siddhant Haldar, Lerrel Pinto, Raunaq Bhirangi. **2024 arXiv preprint.** [Paper](https://arxiv.org/html/2410.17246v1)

Real xArm7 gripper, one AnySkin-equipped finger. Raw 15-dimensional tactile observations become tokens in a transformer imitation policy. Four contact-rich tasks show an average **27.5 percentage-point** improvement over vision-only learning. This is strong policy-input evidence, but not dexterous-hand evidence.

**WowSkin:** no independent research-adoption papers were verified. A1–A2 concern AnySkin, not automatically WowSkin.

### eFlesh — one verified core paper

**E1. eFlesh: Highly Customizable Magnetic Touch Sensing Using Cut-Cell Microstructures.**  
Venkatesh Pattabiraman, Zizhou Huang, Daniele Panozzo, Denis Zorin, Lerrel Pinto, Raunaq Bhirangi. **2025 arXiv preprint.** [Paper](https://arxiv.org/html/2506.09994v1)

Printed magnetic tactile structures on real grippers support transformer-based contact-rich imitation and slip-related learning. Raw magnetic input is used rather than requiring a universally calibrated force map. Demonstrated learning benefits justify investigation, but neither LEAP deployment nor a mature multi-paper adoption record was established.

### ReSkin and derivatives — three papers

**R1. ReSkin: Versatile, Replaceable, Lasting Tactile Skins.**  
Raunaq Bhirangi, Tess Hellebrekers, Carmel Majidi, Abhinav Gupta. **CoRL 2021; proceedings published 2022.** [Paper](https://proceedings.mlr.press/v164/bhirangi22a.html)

Foundational replaceable magnetic-skin work. Bench and robot experiments study sensing, calibration, and replacement. Relevant to transferable tactile representations, but not direct LEAP policy learning.

**R2. All the Feels: A Dexterous Hand with Large Area Sensing.**  
Raunaq Bhirangi, Abigail DeFranco, Jacob Adkins, Carmel Majidi, Abhinav Gupta, Tess Hellebrekers, Vikash Kumar. **RA-L 2023.** [Paper](https://arxiv.org/html/2210.15658v1)

D’Manus three-finger hand with 56 magnetometers across fingers and palm. MLP/LSTM models classify properties and support real sorting demonstrations. Establishes large-area sensing feasibility; does not establish learned LEAP in-hand manipulation.

**R3. Learning In-Hand Translation Using Tactile Skin With Shear and Normal Force Sensing.**  
Jessica Yin, Haozhi Qi, Jitendra Malik, James Pikul, Mark Yim, Tess Hellebrekers. **ICRA 2025.** [Paper](https://arxiv.org/html/2407.07885v1)

Allegro with a sixteen-magnetometer palm skin. PPO-based training and teacher–student transfer use discretized normal/shear observations plus proprioceptive history. Real comparisons against reduced tactile modalities make this one of the most relevant studies for your tactile/proprioceptive objective.

### DIGIT — four relevant papers/sources

**D1. DIGIT: A Novel Design for a Low-Cost Compact High-Resolution Tactile Sensor with Application to In-Hand Manipulation.**  
Mike Lambeta, Po-Wei Chou, Stephen Tian, Brian Yang, B. Maloon, Victoria Rose Most, Dave Stroud, Raymond Santos, Ahmad Byagowi, Gregg Kammerer, Dinesh Jayaraman, Roberto Calandra. **RA-L 2020.** [Paper](https://www.seas.upenn.edu/~dineshj/publication/lambeta-2020-digit/lambeta-2020-digit.pdf)

Real Allegro fingertip manipulation of a marble. A learned tactile dynamics model supports control. Foundational direct dexterous-manipulation evidence; original bulk-manufacturing BOM estimates should not be confused with current retail pricing.

**D2. NeuralFeels with Neural Fields: Visuotactile Perception for In-Hand Manipulation.**  
Sudharshan Suresh, Haozhi Qi, Tingfan Wu, Taosha Fan, Luis Pineda, Mike Lambeta, Jitendra Malik, Mrinal Kalakrishnan, Roberto Calandra, Michael Kaess, Joseph Ortiz, Mustafa Mukadam. **Science Robotics 2024.** [Paper](https://arxiv.org/html/2312.13469v1)

Real Allegro/Panda with four DIGIT fingertips. Tactile depth and vision feed neural-field object reconstruction and tracking. **The manipulation policy is proprioceptive:** this paper demonstrates tactile perception benefit, not tactile-conditioned policy improvement.

**D3. Sparsh: Self-supervised Touch Representations for Vision-Based Tactile Sensing.**  
Higuera and colleagues, full author list under G3. **CoRL 2024.** [Paper](https://openreview.net/forum?id=xYJn2e1uu8)

Includes DIGIT datasets and dexterous-hand perception tasks. Useful pretrained encoders and benchmarks; distinguish encoder evaluation from closed-loop manipulation success.

**D4. Feeling the Future: Dexterous Bolt Manipulation in Robotics Using Optical Tactile Sensing.**  
Catherine M. Ruiz. **2026 senior thesis, Princeton University.** [Institutional record](https://theses-dissertations.princeton.edu/entities/publication/270fe74d-920c-4efd-988f-675149fe98ae)

Real three-finger LEAP redesign with two DIGIT sensors and FR3. Uses tactile contact features for bolt-related learning. The abstract reports reduced validation loss and a threading classifier; the restricted full text prevents a complete independent hardware/ablation audit.

**Separate platform:** *Tactile Beyond Pixels: Multisensory Touch Representations for Robot Manipulation*, Carolina Higuera, Akash Sharma, Taosha Fan, Chaithanya Krishna Bodduluri, Byron Boots, Michael Kaess, Mike Lambeta, Tingfan Wu, Zixi Liu, Francois Robert Hogan, Mustafa Mukadam, **CoRL 2025**, uses **DIGIT360** on Allegro. It is relevant multimodal research, but not evidence about original DIGIT hardware. [Proceedings](https://proceedings.mlr.press/v305/higuera25a.html)

### 9DTact — two papers

**N1. 9DTact: A Compact Vision-Based Tactile Sensor for Accurate 3D Shape Reconstruction and Generalizable 6D Force Estimation.**  
Changyi Lin, Han Zhang, Jikai Xu, Lei Wu, Huazhe Xu. **RA-L 2023 / ICRA 2024 presentation.** [Paper](https://arxiv.org/abs/2308.14277)

Sensor characterization and learning from tactile images; shape recovery and a learned six-dimensional wrench estimator. This is sensor capability evidence, not a LEAP policy result.

**N2. ViHaTeleop: A Low-Cost, Lightweight Visual-Haptic Teleoperation System for Dexterous Manipulation Learning.**  
Fucai Zhu, Yanhou Lai, Paul Maestre, Koichi Hashimoto. **2026 arXiv preprint.** [Paper](https://arxiv.org/html/2608.16572v1)

Real LEAP/FR3, three tactile fingertips, deformation-driven human haptic feedback. Two study tasks are real and four simulated. The downstream imitation-learning improvements are simulated and should not be reported as real autonomous LEAP success.

### TwinTac — two papers

**T1. TwinTac: A Wide-Range, Highly Sensitive Tactile Sensor with Real-to-Sim Digital Twin Sensor Model.**  
Xiyan Huang, Zhe Xu, Chenxi Xiao. **IROS 2025.** [Paper](https://arxiv.org/html/2509.10063v1)

Eight embedded MEMS pressure sensors, molded elastomer, and a finite-element digital twin. Characterization and recognition experiments establish the sensor model; not a dexterous policy comparison.

**T2. Blind Dexterous Grasping via Real2Sim2Real Tactile Policy Learning.**  
Shengcheng Luo, Xiyan Huang, Zhe Xu, Wanlin Li, Ziyuan Jiao, Chenxi Xiao. **2026 arXiv preprint.** [Paper](https://arxiv.org/html/2606.11767v1)

Real LEAP with four curved TwinTac tips plus FSR coverage. Binary contact observations drive a distilled diffusion policy. Calibration ablation is persuasive, but absolute real success remains modest and distributed shear is not used.

### Bio-Skin — one paper plus a later LEAP demonstration

**B1. Bio-Skin: A Cost-Effective Thermostatic Tactile Sensor with Multi-Modal Force and Temperature Detection.**  
Haoran Guo, Haoyang Wang, Zhengxiong Li, Lingfeng Tao. **IROS 2025.** [Project and paper links](https://williamalexanda.github.io/Bio-Skin/)

Real Allegro experiments use combined magnetic, piezoresistive, and thermal sensing. The project separately shows LEAP mounting. No verified LEAP tactile-conditioned policy ablation was found.

### DenseTact / TensorTouch — three related, distinct systems

**C1. DenseTact-Mini: An Optical Tactile Sensor for Grasping Multi-Scale Objects From Flat Surfaces.**  
Won Kyung Do, Ankush Kundan Dhawan, Mathilda Kitzmann, Monroe Kennedy III. **ICRA 2024.** [Paper](https://arxiv.org/html/2309.08860v1)

Real Allegro small-object grasping with specialized tactile tips and nail-assisted strategies. Image-based contact checks support a state machine; this is not a learned LEAP policy benchmark.

**C2. Inter-finger Small Object Manipulation with DenseTact Optical Tactile Sensor.**  
Won Kyung Do, Bianca Aumann, Camille Chungyoun, Monroe Kennedy III. **RA-L 2024, published online 2023.** [Paper](https://arxiv.org/html/2308.16480v1)

Custom two-finger rolling gripper, DenseTact 2.0 tips, tactile point clouds, geometric control, and classification. Real manipulation demonstrates curved optical sensing utility on a different mechanism.

**C3. TensorTouch: Calibration of Tactile Sensors for High Resolution Stress Tensor and Deformation for Dexterous Manipulation.**  
Won Kyung Do, Matthew Strong, Aiden Swann, Boshu Lei, Monroe Kennedy III. **2025 preprint; author website lists T-RO 2026.** [Paper](https://arxiv.org/html/2506.08291v1)

Custom optical tips, instrumented calibration, finite-element modeling, and a learned deformation/stress estimator support real contact-rich control. The paper text inspected does not establish an exact LEAP model/configuration, so it is not counted as a fully verified LEAP deployment.

### Additional candidates discovered from the literature

- **Tekscan pressure arrays:** *Learning Controlled Separation of Small Objects Between Two Fingers with a Tactile Skin*, Ulf Kasolowsky and Berthold Bäuml, **2026 preprint**. A DLR Hand II uses a 4×4 normal-pressure array with PPO and proprioception for separating small objects. Useful normal-only comparison, but no LEAP evidence. [Paper](https://arxiv.org/html/2605.31486v1)
- **BioTac SP:** *GradTac: Spatio-Temporal Gradient Based Tactile Sensing*, Kanishka Ganguly, Pavan Mantripragada, Chethan M. Parameshwara, Cornelia Fermüller, Nitin J. Sanket, Yiannis Aloimonos, **2022 preprint**. Shadow-hand tactile gradients support slip/contact analysis. Relevant historical infrastructure, but insufficient LEAP support to outrank the shortlist. [Paper](https://arxiv.org/abs/2203.07290)

---

## 7. Policy Input and Tactile Representations

### Distributed force arrays: PaXini and calibrated uSkin

A natural observation is:

\[
T_t=\{(p_i(q_t), f_{i,t},m_i)\}_{i=1}^{N},
\]

where \(p_i\) is taxel position, \(f_i\) the measured/estimated tri-axis force, and \(m_i\) an optional validity or contact mask.

Useful encoders include:

| Representation | Suitable model | Main advantage | Main risk |
|---|---|---|---|
| Flattened force vector | MLP | Simple, fast baseline | Tied to a fixed layout |
| Per-pad force map | CNN | Local spatial structure | Artificial adjacency when pads are packed into one image |
| Position/force tokens | Transformer or graph network | Preserves hand geometry | Requires reliable spatial calibration and adequate data |
| Temporal taxel tokens | Temporal transformer / recurrent encoder | Captures loading, relaxation, and slip-related changes | Timestamp and latency errors become consequential |
| Learned tactile embedding | Pretrained encoder + policy | Data efficiency | Pretraining distribution may mismatch the task |

3DTacDex, AdapTac, and the uSkin representation papers provide concrete implementations of these choices.

### Magnetic skins: AnySkin, ReSkin, eFlesh

Their native signal is generally:

\[
B_t\in\mathbb{R}^{N_m\times3},
\]

**not automatically force in newtons.**

A useful policy can consume baseline-subtracted magnetic readings and a short history without explicit force calibration. ViSk demonstrates this strategy. For interpretable force control or cross-hardware comparison, calibration becomes much more important.

Preserve:

- Raw magnetic values.
- Baseline and temperature information where available.
- Skin identity and replacement history.
- Sensor-frame geometry.
- Acquisition timestamps.

### Optical tactile sensing

A typical pipeline is:

\[
I_t \rightarrow
\begin{cases}
z_t & \text{learned embedding}\\
D_t & \text{contact depth/geometry}\\
\hat f_t,\hat s_t & \text{learned force/slip estimates}
\end{cases}
\rightarrow \pi(q_t,\dot q_t,\cdot).
\]

Use raw images when representation learning is central. Use geometry or compact features when the task has clear structure, such as cable orientation. Sparsh provides an existing representation starting point; NeuralFeels illustrates tactile geometry for object-state estimation.

**Do not equate an optical sensor’s pixel count with independent force measurements.** Likewise, a learned six-axis wrench is one net force/torque estimate, not six measurements at every contact location.

### Recommended experimental design

For your project, compare the following using the **same hardware and controller**:

1. Proprioception only.
2. Proprioception plus binary contact.
3. Proprioception plus normal-related sensing.
4. Proprioception plus full tri-axis tactile information.
5. The same signals with spatial and temporal encoding.

Then test held-out objects, different days, replacement skins, altered friction, and partial sensor dropout.

This isolates the contribution of tactile information and representation more convincingly than comparing unrelated sensor systems.

---

## 8. Practical LEAP Integration

### Fingertips

Begin with fingertips when the task is precision grasping, reorientation, or slip recovery. Check the complete fingertip envelope, not only the active sensing surface.

A mount must preserve opposing-finger contact and avoid collisions through the full joint range. Added thickness changes reachable grasps and the correspondence between simulated and real contact geometry.

### Finger pads and phalanges

Pad coverage is especially valuable when objects roll or transfer contact away from the tip. A fingertip-only configuration can become effectively blind during these transitions.

PaXini’s tip-plus-pad research configuration is a useful precedent. XELA provides broader documented coverage, while custom skins offer more freedom at greater engineering cost.

### Palm

Palm sensing matters for enveloping grasps and palm-supported translation. The ReSkin-derived Allegro translation work makes this particularly relevant to tactile/proprioceptive research.

Do not add palm sensing solely to maximize channel count: first establish that the planned tasks make meaningful palm contact.

### Wiring and communication

XELA documents consolidated hand-level wiring. For custom magnetic arrays, account for bus addressing, multiplexing, acquisition scheduling, and strain relief. Multiple USB optical sensors require practical testing of controller bandwidth, power, cable movement, and dropped frames.

For all systems, measure **contact-to-policy latency and jitter**. A nominal sampling rate does not answer that question.

### Compute

Compact magnetic/force arrays can support inexpensive low-latency encoders. Optical sensing may require several image streams plus reconstruction or feature extraction. Benchmark the complete pipeline on the intended computer before choosing the control rate.

Record tactile and joint signals independently at their useful acquisition rates, then synchronize explicitly. Do not discard high-rate observations merely because the initial policy runs slowly.

### Fast prototype candidates

| Route | Why it can be quick | Qualification |
|---|---|---|
| **Factory-integrated XELA LEAP** | Existing geometry, wiring, and supported acquisition | Lead time and package details require a quote |
| **Two GelSight Minis using the cable-following hardware as a reference** | Purchasable sensors and published implementation | Best for slower geometry/contact experiments |
| **Research-matched PaXini package** | Closest path to reproducing published LEAP learning | Quick only if exact mounts/electronics/API are available |
| **Purchased AnySkin-compatible/WowSkin kit** | Small raw observation space and open software | Verify stock and LEAP adapter; do not assume vendor equivalence to research hardware |

For an AnySkin prototype, four fingertip modules would provide **60 raw magnetic channels** with five three-axis magnetometers each. That is a proposed configuration, not a published LEAP benchmark.

---

## 9. Cost and Procurement

Prices below are public listings or explicitly identified historical figures, excluding tax, shipping, host computer, robot arm, and custom engineering.

| Candidate | Per-sensor / package information | Reasonable LEAP configuration | Reliable system-level estimate |
|---|---|---|---|
| **XELA uSkin** | Quote required | Integrated full hand or partial coverage | **Quote required / not publicly disclosed** |
| **PaXini** | Quote required for current research-matched modules | Eight modules for the tip/pad precedent, or a qualified alternative | **Quote required / not publicly disclosed** |
| **GelSight Mini system** | **$510** listed | Two or four sensors | **$1,020 / $2,040**, before adapters and USB infrastructure |
| **GelSight Mini robotics package** | **$560** listed | Two or four sensors | **$1,120 / $2,240**, before adapters and USB infrastructure |
| **DIGIT** | **$355** listed | Two-sensor pilot or four fingertips | **$710 / $1,420**, before mounts and USB infrastructure |
| **WowSkin** | Standard variant displays **$128**; other collection prices start lower | Four modules plus adapters/interface | Complete usable configuration and availability not confirmed |
| **AnySkin / ReSkin** | Components and fabrication vary | Four tips; optional pads/palm | No defensible complete current quote established |
| **eFlesh** | Magnets are inexpensive; PCB/printing/labor additional | Four printed tips or custom coverage | Full cost not established |
| **9DTact** | DIY or supplier-built | Three or four fingertips | Supplier quote / current price not verified |
| **TwinTac / Bio-Skin / TensorTouch** | Custom builds | Design-dependent | BOM alone would omit substantial integration/calibration work |

The [GelSight store](https://www.gelsight.com/online-store/) lists Mini replacement gels at **$57 standard / $70 marked**, and DIGIT replacement gels at **$42**. The [Mini robotics package](https://www.gelsight.com/product/gelsight-mini-robotics-package/) includes standard and marked gels and lists an estimated four-week lead time.

**Source conflicts and misleading prices**

- The Mini repository FAQ contains older two-unit prices that differ from the current store. The estimates above use the current transactional listings.
- WowSkin’s [collection page](https://shop.wowrobo.com/collections/sensors-touch) shows “from” pricing that should not be read as the price of a complete LEAP-ready sensor.
- P4 reports roughly **$200 per older PaXini pad**. That is historical research context, not a current quote for the LEAP modules.
- Original DIGIT bulk BOM figures and eFlesh magnet costs are not complete retail-system prices.
- The LEAP v2 demonstration reports inexpensive FSR components—approximately **$2 per sensor plus a $20 board**—but these provide a baseline rather than the rich sensing sought here. [LEAP v2 demonstration](https://www.roboticsproceedings.org/rss21/p132.pdf)

Budget for spare contact surfaces, at least one spare module, mounting revisions, calibration fixtures, and synchronized acquisition. These can matter more operationally than a small difference in sensor purchase price.

---

## 10. Final Top 3 Recommendation

### 1. PaXini distributed tri-axis tactile sensing

**Why it ranks first:** it best satisfies your primary criterion—actual LEAP manipulation research in which rich tactile observations enter the learned policy.

**Strongest evidence:** 3DTacDex and AdapTac, reinforced by the newer cluttered-grasping study.

**What it enables**

- Contact-aware diffusion policies.
- Spatial tactile representation learning.
- Force-conditioned manipulation and grasp stabilization.
- Continuous-versus-binary tactile ablations.
- Studies combining local taxels with proprioceptive or estimated-wrench information.

**Practical limitation:** the research configuration must become an identifiable, purchasable system. Do not order a nominally similar PX-6AX model before verifying geometry, taxel layout, calibration outputs, communications, and mounting.

**Decision:** first choice if the published configuration can be reproduced with supported current hardware.

### 2. XELA uSkin LEAP package

**Why it ranks second:** it combines explicit LEAP support with strong adjacent-hand evidence for exactly the kinds of learning methods you want to study.

**Strongest evidence:** official integration plus T-DEX, See to Touch, and PercepSkin.

**What it enables**

- Whole-hand contact-state estimation.
- Policies that exploit rolling and migrating contacts.
- Tactile play datasets and spatial/temporal pretraining.
- Normal-versus-shear and fingertip-versus-full-hand comparisons.

**Practical limitation:** direct LEAP algorithm validation remains a gap in the literature reviewed.

**Decision:** the strongest choice when minimizing hardware-development uncertainty is more important than reproducing a particular LEAP paper.

### 3. GelSight Mini

**Why it ranks third:** it combines direct peer-reviewed LEAP manipulation evidence, current procurement, public software, and detailed local tactile geometry.

**Strongest evidence:** the LEAP cable-following implementation; additional support from the LEAP thesis and broader optical representation ecosystem.

**What it enables**

- Contact geometry and deformation estimation.
- Tactile-conditioned precision manipulation.
- Optical tactile representation learning.
- Object/contact-state tracking under external visual occlusion.

**Practical limitation:** the observed latency and physical packaging make it a weaker default for fast whole-hand stabilization.

**Decision:** select it when geometry is central; do not choose it merely because images contain more dimensions than force arrays.

### Second-pass verification of the Top 3

| Check | PaXini | XELA uSkin | GelSight Mini |
|---|---|---|---|
| Current product family exists | Confirmed on current GEN3/GEN4 pages | Confirmed | Confirmed |
| Purchase or quote route | Sales/quote route | Quote route | Public purchase listing |
| Strongest LEAP claim reopened | Original 3DTacDex hardware section | Official LEAP integration page | Original cable-following paper |
| Configuration verified | Eight modules, 15 tri-axis taxels each | Documented full-hand configuration | Two sensors, thumb/index |
| Representative research actually uses sensor | Confirmed | Confirmed on Allegro; no LEAP paper claimed | Confirmed |
| Remaining material uncertainty | Exact current SKU matching research | Independent LEAP learning validation | End-to-end performance on your compute/mount |

---

## 11. High-End Recommendation

**If cost is ignored and the sensor is infrastructure, my first procurement conversation would be with XELA about an integrated, individually calibrated LEAP system.** That recommendation concerns implementation risk and support; it does not reverse the literature-first ranking.

In parallel, ask PaXini to supply a package matching an established LEAP research configuration. If it can provide equivalent integration, stable raw/per-taxel access, repeatable calibration, and replacement support, its direct research evidence makes it especially compelling.

For geometry-intensive work, maintain a **separate Mini-equipped fingertip configuration**. A modular arrangement is preferable to committing every finger to optical housings before validating range of motion and latency.

There is insufficient evidence here to recommend BioTac, DIGIT360, or another premium sensor over these options merely because it is expensive or technically sophisticated.

---

## 12. Custom Sensor / Research Extension

Custom sensing is most worthwhile when it tests a specific hypothesis that purchased hardware cannot address.

| Candidate | What must be built | Engineering burden | Plausible secondary contribution |
|---|---|---|---|
| **AnySkin** | Molded/magnetized skin, alignment features, mounts, electronics integration | Medium–high | Policy transfer across replacement skins and finger geometries |
| **ReSkin** | Custom magnetic elastomer, PCB layout, magnetization, calibration | High | Palm/finger coverage and normal/shear representations |
| **eFlesh** | Printed compliant structures, magnet placement, PCB/mount | Medium–high | Mechanical structure co-designed with tactile representation |
| **TwinTac** | PCB, embedded pressure sensors, mold/casting, acquisition | High | Calibrated digital twins and contact-aware sim-to-real |
| **Bio-Skin** | Multimodal layers, thermal components, calibration | High | Force/temperature interaction for material-sensitive manipulation |
| **DenseTact / TensorTouch** | Optical housing, illumination, gel, calibration instrumentation and models | Very high | Dense stress/deformation estimation for dexterous control |

Three research directions are particularly credible:

1. **Morphology-aware tactile representations:** learn representations that transfer across pad locations and hand configurations.
2. **Replaceable-skin policy robustness:** evaluate performance after skin replacement, wear, and changes in compliance.
3. **Task-driven coverage:** determine when palm or phalange sensing adds information beyond fingertips.

For the initial project, I would avoid making fabrication a prerequisite for the first manipulation result. Establish a commercial-sensor baseline, then introduce custom hardware only when it tests a clearly motivated limitation.

---

## 13. Open Questions

### Questions for PaXini

- Which current part numbers match the modules used in 3DTacDex and AdapTac?
- Can the exact LEAP mounts, controllers, and acquisition software be supplied?
- Are per-taxel outputs raw magnetic measurements, calibrated force estimates, or both?
- What is the sustained synchronized rate and measured latency for eight modules?
- Do quoted ranges apply per taxel, per module, or to a derived wrench?
- How are cross-talk, temperature drift, magnetic interference, and replacement skins handled?
- What are SDK licensing, operating-system support, ROS support, and academic pricing?

### Questions for XELA

- What is included in the LEAP package: hand, mounts, controllers, calibration, and replacement surfaces?
- What latency and jitter accompany the advertised full-hand rate?
- What improvement does individual calibration provide over the universal model?
- Which compensation options are included versus additional?
- What is the current delivery status of slip-detection software?
- Can partial coverage be expanded without replacing acquisition hardware?
- Are there unpublished or newly published LEAP manipulation references?

### Questions for GelSight

- What is measured acquisition-to-image and acquisition-to-depth latency on supported hardware?
- Which multi-camera USB configurations are supported?
- What changed with the newer Mini gel formulation, and what durability data apply to it?
- Are maintained LEAP mounts and ROS packages available?
- What calibration is required after gel replacement?
- What force/shear estimates are supported and validated, rather than merely demonstrated in example code?

### Questions for WowSkin and custom-platform suppliers

- Is the complete sensor currently in stock?
- Which listing includes the PCB, skin, controller, cables, and LEAP adapter?
- Is the hardware equivalent to the configuration evaluated in AnySkin?
- Are calibration data, raw protocols, replacement skins, and manufacturing tolerances available?
- Can several units be synchronized and replaced without retraining?

**Recommended next action:** request a research-matched PaXini quote and an integrated XELA quote using the same requirements: distributed tri-axis access, timestamps, calibration documentation, LEAP CAD, replacement parts, and a demonstrated full-hand data stream. Those responses should resolve the most important remaining uncertainty before purchase.