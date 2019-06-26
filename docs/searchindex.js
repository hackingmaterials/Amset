Search.setIndex({docnames:["amset","amset.interpolation","amset.misc","amset.scattering","changelog","contributing","contributors","example_settings","index","installation","license","modules","references","scattering","settings","theory","using"],envversion:{"sphinx.domains.c":1,"sphinx.domains.changeset":1,"sphinx.domains.cpp":1,"sphinx.domains.javascript":1,"sphinx.domains.math":2,"sphinx.domains.python":1,"sphinx.domains.rst":1,"sphinx.domains.std":1,"sphinx.ext.intersphinx":1,sphinx:55},filenames:["amset.rst","amset.interpolation.rst","amset.misc.rst","amset.scattering.rst","changelog.rst","contributing.rst","contributors.rst","example_settings.rst","index.rst","installation.rst","license.rst","modules.rst","references.rst","scattering.rst","settings.rst","theory.rst","using.rst"],objects:{"":{amset:[0,0,0,"-"]},"amset.cli":{main:[0,1,1,""]},"amset.data":{AmsetData:[0,2,1,""]},"amset.data.AmsetData":{calculate_dos:[0,3,1,""],set_doping_and_temperatures:[0,3,1,""],set_extra_kpoints:[0,3,1,""],set_scattering_rates:[0,3,1,""],to_file:[0,3,1,""]},"amset.interpolation":{densify:[1,0,0,"-"],interpolate:[1,0,0,"-"],voronoi:[1,0,0,"-"]},"amset.interpolation.densify":{BandDensifier:[1,2,1,""],fibonacci_sphere:[1,1,1,""],sunflower_sphere:[1,1,1,""]},"amset.interpolation.densify.BandDensifier":{densify:[1,3,1,""]},"amset.interpolation.interpolate":{DFTData:[1,2,1,""],Interpolater:[1,2,1,""]},"amset.interpolation.interpolate.DFTData":{get_lattvec:[1,3,1,""]},"amset.interpolation.interpolate.Interpolater":{get_amset_data:[1,3,1,""],get_dos:[1,3,1,""],get_energies:[1,3,1,""],get_line_mode_band_structure:[1,3,1,""]},"amset.interpolation.voronoi":{PeriodicVoronoi:[1,2,1,""]},"amset.interpolation.voronoi.PeriodicVoronoi":{compute_volumes:[1,3,1,""]},"amset.misc":{constants:[2,0,0,"-"],log:[2,0,0,"-"],util:[2,0,0,"-"]},"amset.misc.log":{WrappingFormatter:[2,2,1,""],initialize_amset_logger:[2,1,1,""],log_banner:[2,1,1,""],log_list:[2,1,1,""],log_time_taken:[2,1,1,""]},"amset.misc.log.WrappingFormatter":{format:[2,3,1,""]},"amset.misc.util":{cast_dict:[2,1,1,""],create_shared_array:[2,1,1,""],df0de:[2,1,1,""],f0:[2,1,1,""],gen_even_slices:[2,1,1,""],groupby:[2,1,1,""],kpoints_to_first_bz:[2,1,1,""],load_settings_from_file:[2,1,1,""],parse_deformation_potential:[2,1,1,""],parse_doping:[2,1,1,""],parse_temperatures:[2,1,1,""],tensor_average:[2,1,1,""],unicodeify_spacegroup:[2,1,1,""],validate_settings:[2,1,1,""],write_settings_to_file:[2,1,1,""]},"amset.run":{AmsetRunner:[0,2,1,""]},"amset.run.AmsetRunner":{from_directory:[0,4,1,""],from_vasprun:[0,4,1,""],from_vasprun_and_settings:[0,4,1,""],run:[0,3,1,""],write_settings:[0,3,1,""]},"amset.scattering":{calculate:[3,0,0,"-"],elastic:[3,0,0,"-"],inelastic:[3,0,0,"-"]},"amset.scattering.calculate":{ScatteringCalculator:[3,2,1,""],calculate_g:[3,1,1,""],get_band_rates:[3,1,1,""],get_ir_band_rates:[3,1,1,""],scattering_worker:[3,1,1,""],w0gauss:[3,1,1,""]},"amset.scattering.calculate.ScatteringCalculator":{calculate_band_rates:[3,3,1,""],calculate_scattering_rates:[3,3,1,""],elastic_scatterers:[3,5,1,""],get_scatterers:[3,4,1,""],inelastic_scatterers:[3,5,1,""],scatterer_labels:[3,5,1,""]},"amset.scattering.elastic":{AbstractElasticScattering:[3,2,1,""],AcousticDeformationPotentialScattering:[3,2,1,""],IonizedImpurityScattering:[3,2,1,""],PiezoelectricScattering:[3,2,1,""]},"amset.scattering.elastic.AbstractElasticScattering":{factor:[3,3,1,""],prefactor:[3,3,1,""]},"amset.scattering.elastic.AcousticDeformationPotentialScattering":{factor:[3,3,1,""],name:[3,5,1,""],prefactor:[3,3,1,""],required_properties:[3,5,1,""]},"amset.scattering.elastic.IonizedImpurityScattering":{factor:[3,3,1,""],name:[3,5,1,""],prefactor:[3,3,1,""],required_properties:[3,5,1,""]},"amset.scattering.elastic.PiezoelectricScattering":{factor:[3,3,1,""],name:[3,5,1,""],prefactor:[3,3,1,""],required_properties:[3,5,1,""]},"amset.scattering.inelastic":{AbstractInelasticScattering:[3,2,1,""],PolarOpticalScattering:[3,2,1,""]},"amset.scattering.inelastic.AbstractInelasticScattering":{factor:[3,3,1,""],prefactor:[3,3,1,""]},"amset.scattering.inelastic.PolarOpticalScattering":{factor:[3,3,1,""],name:[3,5,1,""],prefactor:[3,3,1,""],required_properties:[3,5,1,""]},"amset.transport":{ADOS:[0,1,1,""],AMSETDOS:[0,1,1,""],TransportCalculator:[0,2,1,""]},"amset.transport.TransportCalculator":{solve_bte:[0,3,1,""]},amset:{cli:[0,0,0,"-"],data:[0,0,0,"-"],interpolation:[1,0,0,"-"],misc:[2,0,0,"-"],run:[0,0,0,"-"],scattering:[3,0,0,"-"],transport:[0,0,0,"-"]}},objnames:{"0":["py","module","Python module"],"1":["py","function","Python function"],"2":["py","class","Python class"],"3":["py","method","Python method"],"4":["py","staticmethod","Python static method"],"5":["py","attribute","Python attribute"]},objtypes:{"0":"py:module","1":"py:function","2":"py:class","3":"py:method","4":"py:staticmethod","5":"py:attribute"},terms:{"1e13":14,"1e14":14,"1e15":[7,14],"1e16":[7,14],"1e17":7,"1e18":7,"1e19":7,"1e20":[7,14],"1e21":7,"1x3":1,"20e":16,"2ab":[],"39e":16,"3d2e8b3ec8daf5a27a62":[],"3x3":1,"46e":16,"72e":16,"86e":16,"99e":16,"boolean":[],"byte":[],"case":[13,14,16],"class":[0,1,2,3],"default":[0,2,7,14,16],"final":[],"float":[0,1,2],"fr\u00f6hlich":12,"function":[0,1,10,13,14],"import":16,"int":[1,2,13],"long":[],"new":[0,5,12],"null":7,"return":[0,1,2,3],"static":[0,3,13,14],"true":[0,1,3,7],"try":[],AND:10,ARE:10,BUT:10,DIS:7,DOS:0,Dos:1,FOR:10,For:[1,2,13,14,16],Has:[1,14],NOT:10,Not:14,PRs:5,SUCH:10,THE:10,The:[0,1,2,5,7,8,9,10,13,14,16],There:[],USE:10,Use:5,Using:8,Will:14,___________________________________________________________________________:[],__init__:[],_nlargest:[],_suggest_nbin:0,a_b:[],a_factor:3,abbrevi:13,abc:3,abcd:[],abil:[],about:[0,8,13],abov:[10,13],absolut:[2,5],absorpt:13,abstractelasticscatt:3,abstractinelasticscatt:3,academ:12,accept:[5,14],acceptor:[12,14],acceptor_charg:[3,7],access:13,accord:[2,13],accordingli:9,account:13,accur:8,accuraci:[0,1,7,14],acd:[3,7,13,14],achiev:13,acoust:[8,14],acousticdeformationpotentialscatt:3,across:1,activ:[],actual:5,adapt:5,add:[0,14],added:[2,7,8,13,14],adding:0,addit:[8,14],adjust:1,ado:0,adv:12,advis:10,affect:[7,14],agreement:10,aim:8,alex:6,algorithm:[],alireza:6,all:[0,1,2,5,7,8,10,13,14,16],allow:16,along:[1,16],also:[0,1,13,14],altern:[1,14],alternaitv:[],amen:8,amount:[1,14],amset:[6,7,10,13,14],amset_data:[0,1,3],amset_set:14,amsetdata:[0,1,3],amsetdo:0,amsetrun:0,amsetrunn:[0,16],angl:13,angstrom:7,ani:[0,1,2,5,10,14,16],anoth:[],anubhav:6,anyon:10,api:14,append:2,appli:14,applic:12,approv:10,approxim:[8,13,14],arbitrari:[],area:[5,8],arg:2,argument:[],aris:10,arrai:[0,1],art:8,artifici:14,ask:[],atlassian:[],atom:1,atomic_unit:1,attribut:2,auto:[0,3,7,14],autogener:8,autom:[],automat:[0,1,5,7,14],auxiliari:0,avail:[0,1,8,10,16],averag:14,avoid:5,b_idx:3,backend:[],backend_opt:[],background:5,ball_tre:3,band:[0,1,7,8,13,14,16],band_structur:[0,1],banddensifi:1,bandgap:[1,7],bandstructur:1,bandstructuresymmlin:1,bar:[],bardeen:[12,13],base:[0,1,2,3,7,8,13,14],bash:[],basic:5,batch:[],batch_siz:[],becaus:1,becom:5,befor:2,begin:13,below:[8,10,13,14],berkelei:[6,10],best:[5,8],beta:13,between:[1,13,14],bin:0,binari:10,block:1,bohr:1,boltzmann:[8,14],boltztrap2:[1,8],boltztrap:1,bolztrap2:[1,9],bool:1,bose:13,both:16,bottleneck:[],bottom:13,boundari:13,branch:5,briandk:5,brillouin:[2,8,14],bring:[],broaden:[13,14],bsd:10,bug:10,built:8,busi:10,bytes_limit:[],bz2:[],c_factor:3,cach:[],cache_s:[],cachedir:[],calcul:[0,1,2,7,8,11,13,14,16],calculate_band_r:3,calculate_do:0,calculate_g:3,calculate_in_r:3,calculate_mobl:[0,7],calculate_out_r:3,calculate_scattering_r:3,california:10,call:[0,2,14],can:[1,5,7,8,9,13,14,16],cannot:[1,14],captur:[],career:6,carret:1,carri:2,carrier:[0,8,13,14],cartesian:1,cast_dict:2,caus:10,caution:7,cband:0,cbm:[1,7,14],cell:14,certain:8,chang:[5,8],charg:[12,14],child:[],choic:0,choos:10,cli:11,client:[],clone:9,close:[],cluster:8,code:[8,10,13],codebas:5,codepath:[],coeffici:[13,14],coerce_mmap:[],com:9,combin:[13,14],come:15,comma:14,command:[0,8,14],comment:5,commit:5,common:[8,13],commonli:[],commun:1,compar:5,compil:5,complet:[],compress:[],compressor:[],compressor_nam:[],compressorwrapp:[],compromis:[],comput:[0,1,2,8,10,14],computation:8,compute_volum:1,computin:[],concentr:[7,13,14],concurr:[],conda:9,condit:[10,13],conduct:0,configur:[2,9,16],confirm:5,conjunct:1,consecut:1,consequ:[],consequenti:10,conserv:0,consid:[0,13,14],constant:[0,7,8,11,13,14],constraint:[],construct:[],constructor:[0,1],consum:[],contain:[0,2,13,14],content:11,context:[],contract:10,contribut:[6,13,14],contributor:[5,8,10],control:[1,7,14,16],converg:[14,16],conwel:[12,13],coordin:[1,2],coords_are_cartesian:1,copyright:10,core:1,correct:14,correspond:[13,14],cosin:13,count:[],coupl:[1,2],cpu:1,crai:9,crash:14,craype_link_typ:9,creat:[2,5],create_shared_arrai:2,crystal:12,ctrl:[],current:[5,8,13,16],curvatur:0,custom:[0,2],cut:[1,14],cutoff:14,cxx:9,cython:[],damag:10,data:[2,8,10,11],datastructur:[],datefmt:2,debug:2,decor:[],deep:[],def:[],defect:14,defin:[1,13,14],deform:[8,12,14],deformation_pot_str:2,deformation_potenti:[3,7,13,16],deformation_potential_cbm:7,degre:[1,13],delai:[],delta:[13,14],denser:14,densif:[7,14],densifi:[0,11,14],densifii:[],densiti:[0,1,7,13,14],depart:6,depend:[1,9,13,14],deprec:[],dept:10,depth:[],deriv:[1,2,10,14],descript:[4,13,14],det:[],detail:[1,7,14,16],determin:[0,1,2,7,14],dev:[],develop:[5,6,10,13,14],df0de:2,dft:[8,13,14],dftdata:1,diagram:1,dict:[0,1,2],dictionari:[1,2,14,16],dictionnari:[],didn:5,dielectirc:[],dielectr:[7,8,13,14],diff:[],differ:[1,16],differenti:13,difficult:8,dimens:1,dimensionless:13,dingl:[12,13],dirac:[2,13,14],direct:[1,10,14],directli:[10,14],directori:[0,16],disabl:[],disclaim:10,discret:13,discuss:[],disk:14,dispatch:[],dispers:14,distribut:[2,10,13],doc:0,doctest:[],document:[5,7,10,14,16],doe:2,doesn:1,done:[],donor:[12,14],donor_charg:[3,7],dope:[0,7,16],doping_str:2,dos:[0,14],dos_estep:[0,1,7],dos_weight:0,dos_width:[0,7],down:[],download:[],draft:5,dublin:12,due:13,dump:[],dure:[],dynam:[],each:[0,1,8,13,14],earli:6,easi:[5,8],easier:[],easili:[8,16],eband:0,edg:[],ediff:3,edinburgh:12,efermi:0,effect:[1,14],effective_mass:1,effective_masss:1,effici:[],eig:0,einstein:13,either:10,elaps:[],elast:[0,11,13,14],elastic_const:[3,7,13,16],elastic_r:3,elastic_scatter:3,electron:[0,1,3,8,12,13,14],electronic_structur:[],electronic_thermal_conduct:0,element:[0,5],elsevi:12,emiss:[3,13],enabl:[8,14],encount:5,end:13,endors:10,energi:[0,1,2,6,10,13,14],energy_cutoff:[1,7],enhanc:10,ensur:5,environ:9,epsilon_0:14,epsilon_:13,equal:[13,14],equat:[8,13,14],equilibrium:2,erang:0,error:[2,5,14],estep:[1,14],estim:0,etc:[],evalu:[],even:10,event:[2,10],eventu:[],ever:13,everi:13,everyon:8,exactli:13,exampl:[0,2,5,14,16],example_:[],example_googl:[],example_set:2,example_settings_:[],excel:5,except:[0,2],exchang:[],exclus:10,execut:[],exemplari:10,exist:1,exp:13,expect:5,expens:[0,1,8,14],explan:[],explicitli:[],express:[10,13],extens:[],extra:14,extra_energi:0,extra_kpoint:0,extra_project:0,extra_vveloc:0,facebook:5,factor:[1,3,7,13,14,16],faghaninia:6,fall:[1,5],fals:[0,1,2,3,7],fast:8,faster:1,fd_tol:[3,7],featur:[4,5,8,10],feel:5,fermi:[1,2,7,13,14],fermido:[],few:5,fibonacci_spher:1,field:12,file:[0,2,7,8,14],file_format:[0,7],filenam:2,filepath:2,filesystem:[],find:[5,14],finish:5,finit:13,first:[2,8,9],fit:10,fix:[5,10],flag:14,flexibl:1,flow:5,fly:[],fmt:2,folder:2,follow:[0,5,10,16],followup:5,forc:3,fork:[5,8],form:[10,13],formal:8,format:[1,2,14],formatexcept:2,formatt:2,formattim:2,forum:[],found:8,four:0,frac:13,frac_point:1,fraction:[1,2],framework:5,francesco:6,free:[0,5,10],frequenc:[8,13,14],frohlich:[12,13],from:[0,1,2,5,6,8,10,13,14],from_directori:[0,16],from_vasprun:0,from_vasprun_and_set:[0,16],frost:6,full:[1,5,13,14],full_kpoint:0,fund:6,further:5,futur:[8,13],g_b:13,g_tol:3,gain:[],gamma:14,ganos:6,ganosei:[],gap:[1,7,14],gauss:14,gauss_width:[3,7],gaussian:[0,1,13,14],gen_even_slic:2,gener:[1,2,7,8,13,16],geoffroi:6,get:[1,8],get_amset_data:1,get_band_r:3,get_do:1,get_energi:1,get_ir_band_r:3,get_lattvec:1,get_line_mode_band_structur:1,get_scatter:3,getmessag:2,gil:[],gist:[],git:9,github:[8,9],give:[0,1,13],given:[1,2,7,13,14,16],global:[],going:2,good:[5,10],googl:5,got:8,gpa:[7,14],grant:10,great:[],greater:[14,16],grid:[1,16],group:[0,1,5,6,14],groupbi:2,grouped_ir_to_ful:3,guess:0,guid:5,guidelin:5,gzip:[],hack:6,hackingmateri:9,half:[],handl:[1,8],handler:2,happen:5,hard:[],hartre:1,has:[],hash_nam:[],hautier:6,have:[2,5,13],hbar:13,heapq:[],heavi:5,heavili:8,help:[8,16],helper:[],here:[0,5,7,8,14,16],herebi:10,heurist:[],high:[1,8,12,13,14,16],high_frequency_dielectr:[3,7,13],higher:[],highest:14,highli:8,hint:[],histogram:0,hitchhik:5,hold:[7,14],holder:10,hole:[12,13,14],host:5,how:13,howev:[5,8,10,13],html:[],http:9,human:[],i_factor:16,ibt:14,ibte_tol:7,icc:9,identifi:[],imp:[3,7,13,14],implement:[1,3,5,8,13],impli:10,impos:10,improv:[5,8,14],impur:[8,14],in_rat:3,incident:10,includ:[0,1,5,7,8,10,13,14],incorpor:[5,10],increas:14,index:8,indic:[7,14],indirect:10,individu:14,induc:[],inelast:[0,11,13],inelastic_scatter:3,inequival:1,inform:[1,2,5,8,13],infti:13,initi:[1,2],initialis:0,initialize_amset_logg:2,initio:[],input:[5,8,14,16],insid:9,instal:[8,10],instanc:[0,2],instead:[0,5,16],integ:[],integr:8,inteprolat:1,interband:13,interest:13,interfac:14,intern:[7,14],interpol:[0,7,8,11,13,14,16],interpolat:1,interpolate_factor:1,interpolate_project:1,interpolation_factor:[0,1,7,16],interpret:[],interrupt:10,intervallei:[],intio:[],intraband:13,invers:13,involv:8,ioniz:[8,14],ionizedimpurityscatt:3,iqueu:3,ir_kpoint:0,ir_kpoint_weight:0,ir_kpoints_idx:[0,3],ir_to_full_kpoint_map:0,is_met:0,issu:5,itemgett:[],iter:[8,14],its:[0,5,10,13],itself:0,izip:[],jain:6,jason:6,job:[],joblib:[],joblib_temp_fold:[],json:[0,1,3,7,14],just:14,justif:13,k_diff_sq:3,k_idx:3,k_p_idx:3,keep:[],kei:[],kelvin:[2,14],know:8,kpoint:[1,2,3,14],kpoint_mesh:[0,1],kpoint_norm:3,kpoint_weight:[0,3],kpoints_to_first_bz:2,kpt:13,kwarg:0,lab:6,laboratori:10,lambda_to_tau:0,laptop:8,larg:14,larger:14,last:0,latest:[],lattic:[1,12,13],lattice_matrix:1,lawrenc:[6,10],lbnl:6,lbra:[],lead:14,leav:14,led:6,left:13,length:13,less:[],let:8,level:[1,2,7,14],liabil:10,liabl:10,lib:[],librari:8,licens:5,lifetim:0,like:[8,13],limit:10,line:[0,1,8,14],line_dens:1,linux:[],list:[1,3,5,8,10,14,16],list_str:2,littl:[],load:2,load_settings_from_fil:2,loader:[],local:[],locat:[],lock:[],log:[0,7,8,11,14],log_bann:2,log_error_traceback:7,log_list:2,log_time_taken:2,log_traceback:2,logger:2,logrecord:2,loki:[],london:12,longer:[],look:16,loop:[],loss:10,lot:[],louvain:6,love:5,low:12,lzma:[],madsen:1,mag:12,magmom:1,magnet:1,mai:[9,10],main:[0,5,7,14],maintain:5,make:10,manag:[],mani:5,manipul:[],map:[],marker:[],mass:1,master:5,match:[],materi:[1,6,7,8,10,13,16],material_paramet:0,material_properti:0,materials_properti:3,math:[],mathbf:13,mathrm:13,matrix:[1,8],max:14,max_g_it:3,max_ibte_it:7,max_nbyt:[],max_points_per_chunk:1,maximum:[0,1,14],md5:[],mean:[0,5],meaning:5,mechan:[7,13,14],mechanim:[],megabyt:[],memmap:[],memori:1,menu:16,merchant:10,mesh:[1,7,14],messag:[2,14],met:10,metal:[1,14],meter:[],method:[1,3],methodolog:13,might:5,minimum:0,misc:[0,11],miss:2,mitig:[],mmap_mod:[],mobil:[0,12,14],mode:[0,1],model:[0,8,13],modern:[],modf:[],modif:10,modifi:[7,10],modul:[8,11],moment:1,mommat:1,mon:[],monti:[0,1,3],more:[0,1,5,7,8,13,14,16],most:[1,14],mostli:[],move:5,msonabl:[0,1,3],much:1,multipl:[1,13,16],multiprocess:[],must:[10,13],n_cpu:[],n_job:[],n_pack:2,name:[3,10],napoleon:[],narrow:14,nation:[6,10],nband:[0,1],ndarrai:[1,2],neccesarri:[],necessari:[5,8,16],need:[0,5,9,13],neg:[7,14],neglig:10,neither:10,nelect:0,neq:13,never:[],nkpoint:[0,1,3],nlargest:[],nogil:[],nois:13,non:[10,12],none:[0,1,2,3,14],nor:10,nostrand:12,note:[0,1,5,8,14],notic:10,nov:[],now:13,npt:0,nsplit:3,num:14,num_electron:[0,1],num_extra_kpoint:[1,7],num_step:14,number:[0,1,2,7,13,14],numer:13,numpi:[0,8],nworker:[1,3,7],obj:[],object:[0,1,3],oblig:10,obtain:[0,8,13],occup:2,occur:2,off:[1,14],often:[8,14],omega:13,omega_:13,omit:0,onc:[],one:7,onli:[7,13,14],onlin:7,open:[5,8,10,14],oper:[2,8],operand:2,optic:[8,14],optimis:8,option:[0,1,7,14,16],oqueu:3,orbit:[1,13],order:0,org:[],origin:[],original_mesh:1,other:[0,5,6,10,12],otherwis:[10,13],our:5,out:[2,10],out_rat:3,outer:[0,1],output:[7,8],output_paramet:0,outsid:[],over:[13,14],overal:13,overcom:[],overhead:[],overlap:8,overrid:[14,16],overridden:[],overview:8,owner:10,packag:[8,11],page:[8,13],parallel:1,parallel_backend:[],parallelbackendbas:[],paramet:[0,1,2,7,13,14,16],parse_deformation_potenti:2,parse_dop:2,parse_temperatur:2,particular:10,pass:[0,16],patch:10,path:[0,1,2,16],pathlib:[],percent:14,percentag:14,perform:[1,7,8,10,16],performance_paramet:0,period:[8,13],periodicvoronoi:1,permiss:10,permit:10,perpetu:10,persist:[],person:8,phi_:13,phi_p:13,philo:12,phonon:[8,14],phy:12,physic:1,pickl:[],pid:[],pie:[3,7,13,14],piezeoelectric_coeffici:7,piezoelectr:[8,14],piezoelectric_coeffici:[3,13],piezoelectricscatt:3,pip:9,planck:[],pleas:14,point:[1,2,7,8,13,14,16],polar:[8,12,14],polaropticalscatt:3,pool:[],pop:[3,7,13,14],pop_frequ:[3,7,13],pose:13,posit:[7,14],possibl:[5,7,10],potenti:[8,12,14],pre:[],pre_dispatch:[],prefactor:3,prefer:[],prefix:[0,2],prepar:10,preparatori:2,present:14,press:12,previou:[],primari:[6,8,14,16],primarili:6,prime:13,principl:8,print:[14,16],print_log:7,prior:10,problem:[13,14],procedur:5,process:[8,14],processor:[1,14],procur:10,produc:[],product:[0,1,10],prof:6,profit:10,program:[6,16],progress:5,project:[0,1,13],promot:10,properli:9,properti:[1,8,13,14],propos:5,protocol:[],prove:[],provid:[0,1,5,6,10,14,16],publicli:10,pull:8,purpos:10,push:5,pyc:[],pymatgen:[0,1,8],pypi:[],python2:[],python:[5,8,14],pyvoro:1,qhull:1,question:5,queue:[],quick:5,radiu:1,rais:[],ram:[],random:1,rang:[0,1,14,16],rate:[0,7,8,14,16],rather:14,raw:[],read:8,readabl:[],readthedoc:[],realiti:[],reason:1,receipt:10,reciproc:[1,13],reciprocal_lattice_matrix:3,recommend:14,reconstruct:[],record:2,redistribut:10,reduc:[],refer:[2,13],regent:10,region:14,regist:[],register_parallel_backend:[],regular:[1,16],relax:0,releas:13,reli:[],remain:[],replac:13,repo:5,report:[13,14],repositori:9,reproduc:[5,7,10],request:8,requir:[1,2,7,9,10,13,14],required_properti:3,res:[],research:6,reserv:10,reshap:[],resourc:5,respect:[0,1,13,14],respons:5,rest:1,result:7,retain:10,return_buff:2,return_effective_mass:1,return_project:1,return_usage_stat:0,return_vel_outer_prod:1,return_veloc:1,rev:12,revers:[],review:5,ricci:6,right:[10,13],robust:[],rode:[12,13],roughli:14,royalti:10,rst:0,run:[5,7,8,11,14,16],runner:16,s_a_factor:3,s_b:13,s_c_factor:3,s_energi:3,s_g:3,s_k_weight:3,s_kpoint:3,s_kpoint_norm:3,safer:[],sai:1,same:[0,2,5,13],sampl:[1,5,13],save:[],scatter:[0,7,11,12,14,16],scatterer_label:3,scattering_label:0,scattering_model:0,scattering_r:0,scattering_typ:[0,3,7],scattering_work:3,scatteringcalcul:3,sci:12,scipi:[1,8],scissor:[0,1,7],screen:[8,13],script:0,search:8,second:13,section:[7,8,13,14,16],see:[2,5,7,8,14],seebeck:0,select:[],self:[],semiconductor:12,semimet:12,sent:[],separ:[10,14],separate_scattering_mobl:[0,7],sequenti:[],servic:[5,10],set:[0,1,2,8,16],set_doping_and_temperatur:0,set_extra_kpoint:0,set_scattering_r:0,settings_fil:0,settings_overrid:[0,16],setup:[],sever:[],sha1:[],shall:10,shape:0,share:9,sharedmem:[],shm:[],shocklei:[12,13],should:[5,14],side:[],sigma:[13,14],signatur:[],significantli:[],similarli:[],simpl:13,simpler:[],simultan:7,sinc:[],singh:1,singl:[1,14],situat:[],size:0,skip:[],skip_coeffici:1,sleep:[],slice:2,slow:[],slower:[],slowest:[],smaller:[0,1,14],smear:[0,1,14],snippet:16,soc:[0,1],soft:[],softwar:10,solid:8,solv:[8,14],solve_bt:0,some:[5,8,9,14],someth:8,soon:[14,15],sophist:13,sort:[],sourc:[5,8,10],space:[1,5,14],spacegroup_symbol:2,special:10,specif:[5,10],specifi:[2,9,14,16],speed:[7,14],sphinxcontrib:[],spin:[1,3],spread:14,sqrt:13,stack:5,standalon:16,start:14,starv:[],state:[0,1,5,8,13,14],static_dielectr:[3,7,13,16],stdout:2,step:[0,1,2,5,14],still:5,stop:14,store:[],str:[0,2],straightforward:[],strategi:[],strict:10,string:2,strucrtur:[],structur:[0,1,7,8,13,14,16],stuck:8,style:[2,5,10],sub:[],subject:10,sublicens:10,submit:[5,8],submodul:11,subpackag:11,substitut:10,suffer:[],suffix_mesh:0,sum:1,sum_:13,summari:[5,13,16],summat:13,sunflower_spher:1,sup:[],suppli:7,support:[],supposedli:[],symmetri:[1,14,16],symprec:[1,7],syntax:14,system:[1,9,14],tab:5,take:[0,14],task:[],team:5,tell:8,temp:[],temp_fold:[],temperatur:[0,2,7,16],temperatures_str:2,templat:5,temporari:[],tensor:[1,2],tensor_averag:2,term:13,tess:1,tessel:14,test:[5,14],text:[2,13],than:[1,14],theori:[8,10,13],therefor:13,thereof:10,thermal:[],thi:[0,1,3,5,7,8,10,13,14],think:5,thorough:5,those:[1,14,16],though:[],thread:[],threshold:[],through:[6,8,10,13,16],throughput:8,thu:[],thz:[7,14],time:[0,1,2,5,13,14],timeout:[],timeouterror:[],tip:5,tmp:[],tmpdir:[],to_fil:0,todo:0,togeth:[],tol:14,toler:[1,14],top:8,tort:10,total:13,trace:[1,5],traceback:[2,14],track:[5,8],transistor:12,translat:2,transpar:5,transport:[1,11,12,13,14],transportcalcul:0,treat:1,tri:5,trigger:[],tupl:[0,1],turn:[],tutori:[],two:[0,1,7,13,14],txt:14,type:[0,1,2,3,7,13,14],typeerror:[],typic:[],umklapp:13,undecor:[],under:[5,10],understand:[5,8],unicodeify_spacegroup:2,uniform:[0,8,16],uniform_lambda:0,uniform_tau:0,union:[0,1,3],uniqu:[],unit:[1,14],unitless:[7,14],unittest:5,univers:10,unix:[],unless:[],unlik:13,unreleas:[],unset:[],updat:[0,5],upgrad:10,use:[0,5,8,10,13,14,16],use_symmetri:3,used:[0,1,2,10,13,14,16],useful:[],user:9,user_bandgap:0,user_set:2,uses:2,usestim:2,using:[0,1,2,6,9,13,14,16],usr:[],util:[0,11],valid:1,validate_set:2,valu:[0,1,2,14],van:12,variabl:[],vasp:[1,8],vasprun:[0,16],vb_idx:0,vbm:[1,7,14],veloc:[0,1,14],verbos:[],veri:14,version:4,verstraet:1,via:[9,14,16],virtual:9,volum:[13,14],voronoi:[0,11,14],vvband:0,vvelocities_product:0,w0gauss:3,wai:[5,8,10],want:[5,8],warranti:10,wavefunct:13,weight:[0,14],welcom:5,well:[5,14],were:14,what:5,whatsoev:10,when:[1,5,13,14,16],where:[0,1,2,5,7,8,13,14],whether:[1,2,5,10,14],which:[1,2,7,13,14],why:5,width:[0,1,2,13,14],within:1,without:10,work:[1,5,10],worker:1,workflow:[],would:5,wrap:[],wrappingformatt:2,writabl:[],write:[2,5,14],write_input:7,write_mesh:[0,7],write_set:0,write_settings_to_fil:2,written:[2,10],www:[],xciv:12,xml:16,yaml:[0,2,14,16],yet:[5,14],yield:2,york:12,you:[5,8,9,10,14],your:[5,10],zero:[],zip:[],zlib:[],zone:[2,8,14]},titles:["amset package","amset.interpolation package","amset.misc package","amset.scattering package","Change log","Contributing to AMSET","Contributors","Example settings","AMSET: ab initio scattering and transport","Installation","License","amset","References","Scattering rates","Settings","Theory","Using AMSET"],titleterms:{"new":8,Using:16,aasd:[],acceptor_charg:14,acoust:13,addit:5,amset:[0,1,2,3,5,8,9,11,16],amsetrunn:[],analytical_band_from_bzt1:[],api:[8,16],band_interpol:[],band_parabol:[],band_structur:[],bandgap:14,brillouin:13,bug:5,calcul:3,calculate_mobl:14,chang:4,changelog:[],cli:0,code:5,command:16,constant:2,contact:8,content:[0,1,2,3],contribut:[5,8],contributor:6,data:0,deform:13,deformation_potenti:14,delta:[],densifi:1,detect_peak:[],dirac:[],discuss:5,document:8,donor_charg:14,dope:14,dos_estep:14,dos_width:14,dump:[],elast:3,elastic_const:14,energy_cutoff:14,equat:[],exampl:7,example_set:[],fd_tol:14,file:16,file_format:14,from:[9,16],g_tol:[],gauss_width:14,gener:14,get:5,github:5,great:5,hash:[],help:5,high_frequency_dielectr:14,how:5,ibte_tol:14,impur:13,inelast:3,initio:8,instal:9,integr:13,interpol:1,interpolation_factor:14,introduct:8,ioniz:13,joblib:[],k_integr:[],licens:10,line:16,load:[],log:[2,4],log_error_traceback:14,make:5,manual:8,materi:14,max_g_it:[],max_ibte_it:14,mechan:8,memori:[],misc:2,modif:5,modul:[0,1,2,3],nersc:9,note:13,num_extra_kpoint:14,nworker:14,optic:13,option:[],output:[14,16],overlap:13,overview:13,packag:[0,1,2,3],parallel:[],perform:14,phonon:13,piezoelectr:13,piezoelectric_coeffici:14,polar:13,pop_frequ:14,potenti:13,print_log:14,properti:[],pull:5,pymatgen_loader_for_bzt2:[],pypi:[],python:16,rate:13,refer:[5,12],register_compressor:[],report:5,request:5,requir:[],run:0,scatter:[3,8,13],scattering_typ:14,scissor:14,separate_scattering_mobl:14,set:[7,14],sourc:9,static_dielectr:14,submodul:[0,1,2,3],subpackag:0,summari:[],support:8,symprec:14,tabl:[],temperatur:14,test:[],theori:15,through:5,transport:[0,8],unreleas:4,user:8,util:2,voronoi:1,what:8,write_input:14,write_mesh:14,yaml:[],zone:13}})