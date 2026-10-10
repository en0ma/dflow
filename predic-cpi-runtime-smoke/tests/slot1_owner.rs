//! Real current-state account-owner fixture test. Closed historical records remain synthetic.
use solana_program::{account_info::AccountInfo,entrypoint::ProgramResult,
 instruction::{AccountMeta,Instruction},program::invoke,pubkey::Pubkey};
use solana_program_test::{processor,ProgramTest};
use solana_sdk::{account::Account,signature::{Keypair,Signer},transaction::Transaction};
use serde::Deserialize;
use std::{fs,str::FromStr};
const PREDIC:Pubkey=solana_program::pubkey!("pReDicTmksnPfkfiz33ndSdbe2dY43KYPg4U2dbvHvb");
const CALLER:Pubkey=Pubkey::new_from_array([42u8;32]);
#[derive(Deserialize)] struct Snapshot {accounts:Vec<Entry>}
#[derive(Deserialize)] struct Entry {index:usize,address:String,value:Option<serde_json::Value>}
fn caller(_id:&Pubkey,infos:&[AccountInfo],data:&[u8])->ProgramResult{
 let metas=infos.iter().take(12).map(|a|if a.is_writable{
  AccountMeta::new(*a.key,a.is_signer)
 }else{AccountMeta::new_readonly(*a.key,a.is_signer)}).collect();
 invoke(&Instruction{program_id:PREDIC,accounts:metas,data:data.to_vec()},infos)
}
#[tokio::test]
async fn slot1_predic_owned_fixture_external_cpi() {
 let raw=fs::read_to_string("tests/fixtures/live_accounts.json").expect("CI must export live fixture");
 let snapshot:Snapshot=serde_json::from_str(&raw).unwrap();
 assert_eq!(snapshot.accounts.len(),12);
 let mut test=ProgramTest::new("predictions",PREDIC,None);
 test.prefer_bpf(false);
 test.add_program("native_cpi_probe",CALLER,processor!(caller));
 test.set_compute_max_units(1_000_000);
 let wallet=Keypair::new();
 let market=Pubkey::from_str(&snapshot.accounts[2].address).unwrap();
 let nonce=123456789u64;
 let order=Pubkey::find_program_address(&[b"userOrderEscrow",wallet.pubkey().as_ref(),market.as_ref(),&nonce.to_le_bytes()],&PREDIC).0;
 let mut keys=Vec::new();
 for entry in &snapshot.accounts{
  let key=match entry.index {
   4=>order,7|8|9=>wallet.pubkey(),
   1=>Pubkey::new_from_array([11u8;32]),
   _=>Pubkey::from_str(&entry.address).unwrap(),
  };
  keys.push(key);
  if entry.index==0||entry.index==10||entry.index==11||entry.index==4||entry.index==8||entry.index==9 {continue;}
  if entry.index==7||entry.index==1 {
   test.add_account(key,Account{lamports:10_000_000,data:vec![],owner:if entry.index==1 {PREDIC} else {solana_sdk::system_program::id()},executable:false,rent_epoch:0});
   continue;
  }
  let v=entry.value.as_ref().expect("required live account missing");
  let data=base64::Engine::decode(&base64::engine::general_purpose::STANDARD,v["data"][0].as_str().unwrap()).unwrap();
  test.add_account(key,Account{lamports:v["lamports"].as_u64().unwrap(),
    data,owner:Pubkey::from_str(v["owner"].as_str().unwrap()).unwrap(),
    executable:false,rent_epoch:0});
 }
 let mut ctx=test.start_with_context().await;
 let mut data=[0u8;80];data[..8].copy_from_slice(&64u64.to_le_bytes());
 data[8..16].copy_from_slice(&nonce.to_le_bytes());data[16]=b'Y';
 let metas=keys.iter().enumerate().map(|(i,k)|
  if [3,4,6,7,8,9].contains(&i){AccountMeta::new(*k,[7,8,9].contains(&i))}
  else{AccountMeta::new_readonly(*k,false)}
 ).collect();
 let ix=Instruction{program_id:CALLER,accounts:metas,data:data.to_vec()};
 let tx=Transaction::new_signed_with_payer(&[ix],Some(&ctx.payer.pubkey()),
  &[&ctx.payer,&wallet],ctx.last_blockhash);
 let result=ctx.banks_client.process_transaction(tx).await;
 println!("SLOT1_PREDIC_OWNER_CPI_RESULT={:?}",result);
 assert!(result.is_err(),"Zero-value synthetic OPEN unexpectedly succeeded");
}
