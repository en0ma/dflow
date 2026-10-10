//! Verify historical OPEN's nonce, wallet, market, and actual order PDA as a unit.
use solana_program::pubkey::Pubkey;
use serde::Deserialize;
use std::{fs,str::FromStr};

const PREDIC: Pubkey=solana_program::pubkey!("pReDicTmksnPfkfiz33ndSdbe2dY43KYPg4U2dbvHvb");
#[derive(Deserialize)] struct Audit { transactions: Vec<Tx> }
#[derive(Deserialize)] struct Tx { signature: String, cases: Vec<Case> }
#[derive(Deserialize)] struct Case { nonce:u64, instruction_hex:String, accounts:Vec<Role> }
#[derive(Deserialize)] struct Role { address:String }

#[test]
fn historical_open_pda_bindings() {
 let raw=fs::read_to_string("../reports/predic-cpi/historical-construction.json")
  .expect("Run construction audit before Rust tests");
 let audit:Audit=serde_json::from_str(&raw).unwrap();
 assert_eq!(audit.transactions.len(),2);
 for tx in audit.transactions {
  for case in tx.cases {
   assert_eq!(case.accounts.len(),12);
   let bytes=hex::decode(&case.instruction_hex).unwrap();
   assert_eq!(bytes.len(),80);
   let nonce=u64::from_le_bytes(bytes[8..16].try_into().unwrap());
   assert_eq!(nonce,case.nonce);
   let wallet=Pubkey::from_str(&case.accounts[7].address).unwrap();
   let market=Pubkey::from_str(&case.accounts[2].address).unwrap();
   let expected=Pubkey::from_str(&case.accounts[4].address).unwrap();
   let (derived,bump)=Pubkey::find_program_address(
    &[b"userOrderEscrow",wallet.as_ref(),market.as_ref(),&nonce.to_le_bytes()],&PREDIC);
   println!("HISTORICAL_PDA signature={} nonce={} derived={} observed={} bump={} match={}",
    &tx.signature[..12],nonce,derived,expected,bump,derived==expected);
   assert_eq!(derived,expected,"Historical OPEN PDA seeds/nonce mismatch");
  }
 }
}
