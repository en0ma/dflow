use solana_program::{account_info::AccountInfo, entrypoint::ProgramResult,
    instruction::{AccountMeta,Instruction}, program::invoke, pubkey::Pubkey};
use solana_program_test::{processor,ProgramTest};
use solana_sdk::{account::Account, signature::Signer, transaction::Transaction};

const PREDIC: Pubkey = solana_program::pubkey!("pReDicTmksnPfkfiz33ndSdbe2dY43KYPg4U2dbvHvb");
const CALLER: Pubkey = Pubkey::new_from_array([42u8;32]);
const MARKET: Pubkey = solana_program::pubkey!("GGViDLxL6RRQ4zTydGoiL6NnLugxyDGraydUBAQfo9iX");

fn process(_id: &Pubkey, accounts: &[AccountInfo], data: &[u8]) -> ProgramResult {
    // Preserve the child metas encoded in the parent account sequence.
    // First 12 accounts are forwarded, with the duplicate authority at 7-9.
    let metas: Vec<AccountMeta> = accounts.iter().take(12).map(|a|
        if a.is_writable {AccountMeta::new(*a.key,a.is_signer)}
        else {AccountMeta::new_readonly(*a.key,a.is_signer)}
    ).collect();
    invoke(&Instruction{program_id:PREDIC,accounts:metas,data:data.to_vec()},accounts)
}
#[tokio::test]
async fn cpi_dispatch_with_complete_account_positions() {
    let mut test=ProgramTest::new("predictions",PREDIC,None);
    test.prefer_bpf(false);
    test.add_program("native_cpi_probe",CALLER,processor!(process));
    test.set_compute_max_units(1_000_000);
    let mut ctx=test.start_with_context().await;
    let wallet=ctx.payer.pubkey();
    let order=Pubkey::find_program_address(
        &[b"userOrderEscrow",wallet.as_ref(),MARKET.as_ref(),&123456789u64.to_le_bytes()],
        &PREDIC
    ).0;
    let config=Pubkey::new_unique();
    let vault=Pubkey::new_unique();
    let user_token=Pubkey::new_unique();
    let mint=solana_program::pubkey!("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v");
    // Deliberately synthetic data: distinguish account-count validation from
    // owner/mint/state validation without touching real user funds.
    for key in [config, MARKET, vault, user_token, mint] {
        test.add_account(key,Account{lamports:1_000_000,data:vec![],owner:solana_sdk::system_program::id(),executable:false,rent_epoch:0});
    }
    let mut data=[0u8;80];
    data[..8].copy_from_slice(&64u64.to_le_bytes());
    data[8..16].copy_from_slice(&123456789u64.to_le_bytes());
    data[16]=b'Y';
    let ix=Instruction{
        program_id:CALLER,
        accounts:vec![
            AccountMeta::new_readonly(PREDIC,false),
            AccountMeta::new_readonly(config,false),
            AccountMeta::new_readonly(MARKET,false),
            AccountMeta::new(vault,false),
            AccountMeta::new(order,false),
            AccountMeta::new_readonly(mint,false),
            AccountMeta::new(user_token,false),
            AccountMeta::new(wallet,true),
            AccountMeta::new(wallet,true),
            AccountMeta::new(wallet,true),
            AccountMeta::new_readonly(solana_sdk::spl_token::id(),false),
            AccountMeta::new_readonly(solana_sdk::system_program::id(),false),
        ],
        data:data.to_vec()
    };
    let tx=Transaction::new_signed_with_payer(&[ix],Some(&wallet),&[&ctx.payer],ctx.last_blockhash);
    let result=ctx.banks_client.process_transaction(tx).await;
    assert!(result.is_err(),"Synthetic invalid account fixtures unexpectedly opened an order");
    println!("12-position OPEN CPI result (expected rejection): {:?}",result.err());
}
